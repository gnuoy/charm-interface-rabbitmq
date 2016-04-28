# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest

import requires
import mock


_hook_args = {}


def mock_hook(*args, **kwargs):

    def inner(f):
        # remember what we were passed.  Note that we can't actually determine
        # the class we're attached to, as the decorator only gets the function.
        _hook_args[f.__name__] = dict(args=args, kwargs=kwargs)
        return f
    return inner


class TestRabbitMQRequires(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._patched_hook = mock.patch('charms.reactive.hook', mock_hook)
        cls._patched_hook_started = cls._patched_hook.start()
        # force requires to rerun the mock_hook decorator:
        reload(requires)

    @classmethod
    def tearDownClass(cls):
        cls._patched_hook.stop()
        cls._patched_hook_started = None
        cls._patched_hook = None
        # and fix any breakage we did to the module
        reload(requires)

    def setUp(self):
        self.rmqr = requires.RabbitMQRequires('some-relation', [])
        self._patches = {}
        self._patches_start = {}

    def tearDown(self):
        self.rmqr = None
        for k, v in self._patches.items():
            v.stop()
            setattr(self, k, None)
        self._patches = None
        self._patches_start = None

    def patch_kr(self, attr, return_value=None):
        mocked = mock.patch.object(self.rmqr, attr)
        self._patches[attr] = mocked
        started = mocked.start()
        started.return_value = return_value
        self._patches_start[attr] = started
        setattr(self, attr, started)

    def test_registered_hooks(self):
        # test that the hooks actually registered the relation expressions that
        # are meaningful for this interface: this is to handle regressions.
        # The keys are the function names that the hook attaches to.
        hook_patterns = {
            'joined': ('{requires:rabbitmq}-relation-joined', ),
            'changed': ('{requires:rabbitmq}-relation-changed', ),
            'departed': ('{requires:rabbitmq}-relation-{broken,departed}', ),
        }
        for k, v in _hook_args.items():
            self.assertEqual(hook_patterns[k], v['args'])

    def test_changed(self):
        self.patch_kr('update_state')
        self.rmqr.changed()
        self.update_state.assert_called_once_with()

    def test_joined(self):
        self.patch_kr('update_state')
        self.patch_kr('set_state')
        self.rmqr.joined()
        self.set_state.assert_called_once_with('{relation_name}.connected')

    def test_departed(self):
        self.patch_kr('update_state')
        self.rmqr.departed()
        self.update_state.assert_called_once_with()

    def test_base_data_complete(self):
        self.patch_kr('private_address', '4')
        self.patch_kr('vhost', '5')
        self.patch_kr('username', '6')
        self.patch_kr('password', '7')
        assert self.rmqr.base_data_complete() is True
        self.vhost.return_value = None
        assert self.rmqr.base_data_complete() is False

    def test_ssl_data_complete(self):
        self.patch_kr('ssl_port', '6')
        self.patch_kr('ssl_ca', '7')
        assert self.rmqr.ssl_data_complete() is True
        self.ssl_port.return_value = None
        assert self.rmqr.ssl_data_complete() is False

    def test_request_access(self):
        self.patch_kr('set_local')
        self.patch_kr('set_remote')
        expect = {
            'username': 'bob',
            'vhost': 'neutron',
        }
        self.rmqr.request_access('bob', 'neutron')
        self.set_local.assert_called_once_with(**expect)

    def test_configure(self):
        self.patch_kr('request_access')
        self.rmqr.request_access('bob', 'neutron')
        self.request_access.assert_called_once_with('bob', 'neutron')

    @mock.patch.object(requires, 'hookenv')
    def test_get_remote_all(self, _hookenv):

        class _conversation(object):
            def __init__(self, rids):
                self.relation_ids = rids

        def _relation_get(key, unit, rid):
            rget_values = {
                'pass_unit1_r11': 'pass1',
                'pass_unit2_r11': 'pass2',
                'pass_unit1_r21': 'pass1',
                'pass_unit2_r21': 'pass1',
                'pass_unit1_r31': 'pass2',
                'pass_unit2_r31': 'pass3',
            }
            return rget_values['{}_{}_{}'.format(key, unit, rid)]

        self.patch_kr('conversations')
        _hookenv.related_units.return_value = ['unit1', 'unit2']
        _hookenv.relation_get.side_effect = _relation_get
        self.conversations.return_value = [
            _conversation(['r11']),
            _conversation(['r21', 'r31'])
        ]
        self.assertEqual(
            self.rmqr.get_remote_all('pass'),
            ['pass1', 'pass2', 'pass3']
        )

    def test_rabbitmq_hosts(self):
        self.patch_kr('get_remote_all')
        self.rmqr.rabbitmq_hosts()
        self.get_remote_all.assert_called_once_with('private-address')

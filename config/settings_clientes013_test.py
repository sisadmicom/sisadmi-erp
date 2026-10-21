"""Independent disposable test target. No DEV settings are imported."""
from config.settings_test_r01 import *
from core.testing.clientes013_guard import ENGINE, DATABASE, validate_connections

DATABASES = {'default': {**DATABASES['default'], 'ENGINE': ENGINE, 'NAME': DATABASE,
    'TEST': {'NAME': DATABASE, 'MIRROR': None, 'MIGRATE': True}}}
validate_connections(DATABASES, DATABASE_ROUTERS)
TEST_RUNNER = 'core.testing.clientes013_runner.Clientes013TestRunner'

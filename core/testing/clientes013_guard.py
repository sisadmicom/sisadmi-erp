"""Exact destination policy; no bootstrap or production fallback."""
import os
from django.core.exceptions import ImproperlyConfigured

ENGINE = 'core.testing.clientes013_postgresql'
DATABASE = 'test_sisadmi_clientes013'
USER = 'sisadmi_erp_test_runner'
HOST = '127.0.0.1'
PORT = '5432'

def reject():
    raise ImproperlyConfigured('CLIENTES-01.3 rejected destination, privileges or execution authorization.')

def validate_database(cfg, alias='default'):
    if (alias != 'default' or cfg.get('ENGINE') != ENGINE or cfg.get('NAME') != DATABASE
            or cfg.get('USER') != USER or cfg.get('HOST') != HOST or str(cfg.get('PORT')) != PORT
            or not cfg.get('PASSWORD') or cfg.get('CONN_MAX_AGE', 0) != 0
            or cfg.get('CONN_HEALTH_CHECKS', False)
            or cfg.get('OPTIONS') != {'connect_timeout': 5, 'sslmode': 'disable'}
            or cfg.get('TEST', {}).get('NAME') != DATABASE or cfg.get('TEST', {}).get('MIRROR')
            or cfg.get('TEST', {}).get('MIGRATE', True) is not True):
        reject()

def validate_connections(databases, routers):
    if set(databases) != {'default'} or routers:
        reject()
    validate_database(databases['default'])

def require_execution():
    if os.environ.get('CLIENTES013_ALLOW_TEST_EXECUTION') != '1' or any(k.startswith('PG') for k in os.environ):
        reject()

def verify_identity(cursor):
    cursor.execute('SELECT current_database(),current_user,inet_server_addr()::text,inet_server_port()')
    if cursor.fetchone() != (DATABASE, USER, HOST+'/32', int(PORT)):
        reject()
    cursor.execute('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')
    if cursor.fetchone() != (USER,):
        reject()
    cursor.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user')
    if cursor.fetchone() != (False,)*5:
        reject()
    cursor.execute('SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=current_user')
    if cursor.fetchone() is not None:
        reject()
    cursor.execute("SELECT has_database_privilege(current_user,current_database(),'CONNECT'),has_schema_privilege(current_user,'public','CREATE')")
    if cursor.fetchone() != (True, True):
        reject()

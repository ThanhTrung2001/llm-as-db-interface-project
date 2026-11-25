import os
import tempfile

# CSDL ứng dụng riêng cho test — phải đặt trước khi import app.backend.config
_tmp = tempfile.mkdtemp(prefix='clubquery_')
os.environ['CLUBQUERY_APP_DB'] = os.path.join(_tmp, 'app_test.sqlite')
os.environ['CLUBQUERY_CLUB_DB'] = os.path.join(_tmp, 'club_test.sqlite')
os.environ.setdefault('CLUBQUERY_TRACE', '0')

import pytest  # noqa: E402

from app.backend import appdb  # noqa: E402


@pytest.fixture(scope='session', autouse=True)
def fresh_db():
    appdb.init_db(reset=True)
    yield


@pytest.fixture
def conn():
    c = appdb.connect()
    yield c
    c.close()

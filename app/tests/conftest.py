import os
import tempfile

# CSDL ứng dụng riêng cho test — phải đặt trước khi import app.backend.config
os.environ['CLUBQUERY_APP_DB'] = os.path.join(tempfile.mkdtemp(prefix='clubquery_'), 'app_test.sqlite')
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

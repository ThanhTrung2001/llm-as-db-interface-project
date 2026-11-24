import os
import sys
import tempfile

# Chỉ test mới import script benchmark của BIRD (để so app có làm giống benchmark không); app thì không.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'DAMO-ConvAI', 'bird', 'llm', 'src'))

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

# Copyright The OpenTelemetry Authors
#
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

import types
from unittest import mock

import psycopg2

import opentelemetry.instrumentation.psycopg2
from opentelemetry import trace
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk import resources
from opentelemetry.test.test_base import TestBase


class MockCursor:
    execute = mock.MagicMock(spec=types.MethodType)
    execute.__name__ = "execute"

    executemany = mock.MagicMock(spec=types.MethodType)
    executemany.__name__ = "executemany"

    callproc = mock.MagicMock(spec=types.MethodType)
    callproc.__name__ = "callproc"

    rowcount = "SomeRowCount"

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self


class MockConnection:
    commit = mock.MagicMock(spec=types.MethodType)
    commit.__name__ = "commit"

    rollback = mock.MagicMock(spec=types.MethodType)
    rollback.__name__ = "rollback"

    def __init__(self, *args, **kwargs):
        self.cursor_factory = kwargs.pop("cursor_factory", None)
        self._initialized = True

    def cursor(self):
        if self.cursor_factory:
            return self.cursor_factory(self)
        return MockCursor()

    def get_dsn_parameters(self):  # pylint: disable=no-self-use
        return {"dbname": "test"}

    def __setattr__(self, name, value):
        """
        This method is overridden to prevent adding new attributes to the MockConnection object.
        At runtime, the psycopg2 connection object does not have attribute
        _is_instrumented_by_opentelemetry, it will throw AttributeError when setting this
        attribute.
        """
        if hasattr(self, '_initialized') and not hasattr(self, name):
            raise AttributeError(f"Cannot add new attribute '{name}' to MockConnection")
        super().__setattr__(name, value)


class TestPostgresqlIntegration(TestBase):
    def setUp(self):
        super().setUp()
        self.cursor_mock = mock.patch(
            "opentelemetry.instrumentation.psycopg2.pg_cursor", MockCursor
        )
        self.connection_mock = mock.patch("psycopg2.connect", MockConnection)

        self.cursor_mock.start()
        self.connection_mock.start()

    def tearDown(self):
        super().tearDown()
        self.memory_exporter.clear()
        self.cursor_mock.stop()
        self.connection_mock.stop()
        with self.disable_logging():
            Psycopg2Instrumentor().uninstrument()

    # pylint: disable=unused-argument
    def test_instrumentor(self):
        Psycopg2Instrumentor().instrument()

        cnx = psycopg2.connect(database="test")

        cursor = cnx.cursor()

        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.psycopg2
        )

        # check that no spans are generated after uninstrument
        Psycopg2Instrumentor().uninstrument()

        cnx = psycopg2.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_span_name(self):
        Psycopg2Instrumentor().instrument()

        cnx = psycopg2.connect(database="test")

        cursor = cnx.cursor()

        cursor.execute("Test query", ("param1Value", False))
        cursor.execute(
            """multi
        line
        query"""
        )
        cursor.execute("tab\tseparated query")
        cursor.execute("/* leading comment */ query")
        cursor.execute("/* leading comment */ query /* trailing comment */")
        cursor.execute("query /* trailing comment */")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 6)
        self.assertEqual(spans_list[0].name, "Test")
        self.assertEqual(spans_list[1].name, "multi")
        self.assertEqual(spans_list[2].name, "tab")
        self.assertEqual(spans_list[3].name, "query")
        self.assertEqual(spans_list[4].name, "query")
        self.assertEqual(spans_list[5].name, "query")

    # pylint: disable=unused-argument
    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        Psycopg2Instrumentor().instrument()
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            cnx = psycopg2.connect(database="test")
            cursor = cnx.cursor()
            query = "SELECT * FROM test"
            cursor.execute(query)
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

        Psycopg2Instrumentor().uninstrument()

    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        Psycopg2Instrumentor().instrument(tracer_provider=tracer_provider)

        cnx = psycopg2.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    # pylint: disable=unused-argument
    def test_instrument_connection(self):
        cnx = psycopg2.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = Psycopg2Instrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_instrument_connection_with_instrument(self):
        cnx = psycopg2.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        Psycopg2Instrumentor().instrument()
        cnx = Psycopg2Instrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_uninstrument_connection_with_instrument(self):
        Psycopg2Instrumentor().instrument()
        cnx = psycopg2.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = Psycopg2Instrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_uninstrument_connection_with_instrument_connection(self):
        cnx = psycopg2.connect(database="test")
        cnx = Psycopg2Instrumentor().instrument_connection(cnx)
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = Psycopg2Instrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_sqlcommenter_enabled(self, event_mocked):
        cnx = psycopg2.connect(database="test")
        Psycopg2Instrumentor().instrument(enable_commenter=True)
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)
        kwargs = event_mocked.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_sqlcommenter_disabled(self, event_mocked):
        cnx = psycopg2.connect(database="test")
        Psycopg2Instrumentor().instrument()
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)
        kwargs = event_mocked.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], False)

    def test_no_op_tracer_provider(self):
        Psycopg2Instrumentor().instrument(
            tracer_provider=trace.NoOpTracerProvider()
        )
        cnx = psycopg2.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

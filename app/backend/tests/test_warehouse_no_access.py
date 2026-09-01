"""Permission-denied from the warehouse becomes WarehousePermissionError,
whether it arrives as a raised SDK exception or a FAILED statement status."""

from types import SimpleNamespace

import pytest
from databricks.sdk.errors import PermissionDenied
from databricks.sdk.service.sql import StatementState

from backend.warehouse import WarehouseError, WarehousePermissionError, run_query


def test_sdk_permission_denied_exception_maps(mock_client):
    mock_client.statement_execution.execute_statement.side_effect = PermissionDenied("nope")
    with pytest.raises(WarehousePermissionError):
        run_query(mock_client, "SELECT 1")


def test_failed_statement_with_insufficient_permissions_maps(mock_client):
    mock_client.statement_execution.execute_statement.return_value = SimpleNamespace(
        status=SimpleNamespace(
            state=StatementState.FAILED,
            error=SimpleNamespace(
                error_code="INSUFFICIENT_PERMISSIONS",
                message="Insufficient privileges: user does not have SELECT",
            ),
        ),
        manifest=None,
        result=None,
        statement_id="stmt-1",
    )
    with pytest.raises(WarehousePermissionError):
        run_query(mock_client, "SELECT 1")


def test_ordinary_failure_still_plain_warehouse_error(mock_client):
    mock_client.statement_execution.execute_statement.side_effect = Exception("warehouse unreachable")
    with pytest.raises(WarehouseError) as excinfo:
        run_query(mock_client, "SELECT 1")
    assert not isinstance(excinfo.value, WarehousePermissionError)

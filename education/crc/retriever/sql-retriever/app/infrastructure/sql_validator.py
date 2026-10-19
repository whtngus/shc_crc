"""S-R4 SQL 검증 규칙(부록 31장)을 sqlglot 문법 트리로 검사하는 구현체.

문자열 비교가 아니라 문법 트리로 검사함(15장). 허용 목록에 있는 것만 통과시킴(기본 거부).
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import TokenType

from ..application.models import ValidationResult
from ..application.ports import SqlValidatorPort
from ..domain.catalog import (
    ALLOWED_FUNCTIONS,
    ALLOWED_SCHEMA,
    ALLOWED_VIEWS,
    FORBIDDEN_FUNCTION_PREFIX,
    FORBIDDEN_FUNCTIONS,
    FORBIDDEN_SCHEMAS,
    ROW_LIMIT,
)

DIALECT = "postgres"

# sqlglot은 PostgreSQL 함수를 표준 노드로 바꿔 읽음(예: to_char → TimeToStr, date_trunc → TimestampTrunc).
# 그래서 허용 함수 이름을 sqlglot 노드 종류로 옮겨 적음. 이 표에 없는 함수 노드는 모두 거부함
_ALLOWED_FUNCTION_NODES: dict[type[exp.Expression], str] = {
    exp.Count: "count",
    exp.Sum: "sum",
    exp.Avg: "avg",
    exp.Min: "min",
    exp.Max: "max",
    exp.TimestampTrunc: "date_trunc",
    exp.DateTrunc: "date_trunc",
    exp.TimeToStr: "to_char",
    exp.ToChar: "to_char",
    exp.Extract: "extract",
    exp.Coalesce: "coalesce",
    exp.Round: "round",
    exp.Greatest: "greatest",
    exp.Least: "least",
    exp.Abs: "abs",
}
_CAST_NODES: tuple[type[exp.Expression], ...] = (exp.Cast, exp.TryCast)  # 형변환(CAST, ::)
# sqlglot이 함수 노드로 분류하지만 실제로는 연산자나 식인 것. 함수 허용 목록 검사에서 뺌
_OPERATOR_NODES: tuple[type[exp.Expression], ...] = (
    exp.And, exp.Or, exp.Not, exp.Exists, exp.Case, exp.If, exp.Paren,
)
# 쓰기와 구조 변경(31장 금지 1번). 하위 질의 안에 숨어 있어도 찾아냄
_WRITE_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Alter, exp.Drop,
    exp.TruncateTable, exp.Grant, exp.Revoke, exp.Copy, exp.Command,
)
# 31장 허용 구문 목록에 없는 구문. 기본 거부 원칙에 따라 막음
_UNLISTED_SYNTAX_NODES: tuple[type[exp.Expression], ...] = (
    exp.Union, exp.Intersect, exp.Except, exp.Window, exp.Lateral, exp.Values, exp.TableSample,
)
_SET_RETURNING_NODES: tuple[type[exp.Expression], ...] = (
    exp.GenerateSeries, exp.ExplodingGenerateSeries,
)


class SqlglotValidator(SqlValidatorPort):
    """SqlValidatorPort 구현체. 검사 규칙 값은 domain.catalog에서 가져옴."""

    def validate(self, sql: str) -> ValidationResult:
        """SQL 한 문장을 검사하고 LIMIT을 200 이하로 맞춤. 실패하면 사유 코드만 돌려줌."""
        try:
            return self._validate(sql)
        except (ParseError, TokenError):
            return ValidationResult(ok=False, reason="PARSE_ERROR")

    def _validate(self, sql: str) -> ValidationResult:
        if not isinstance(sql, str) or sql.strip() == "":
            return _fail("EMPTY_SQL")

        # 주석과 세미콜론은 문법 트리에서 사라지므로 토큰 단계에서 먼저 봄(문자열 값 안의 기호는 토큰이 아님)
        tokens = sqlglot.tokenize(sql, read=DIALECT)
        if any(token.comments for token in tokens):
            return _fail("COMMENT_NOT_ALLOWED")
        if any(token.token_type == TokenType.SEMICOLON for token in tokens):
            return _fail("MULTIPLE_STATEMENTS")

        statements = [tree for tree in sqlglot.parse(sql, read=DIALECT) if tree is not None]
        if len(statements) != 1:
            return _fail("MULTIPLE_STATEMENTS")
        tree = statements[0]

        if isinstance(tree, _WRITE_NODES) or any(True for _ in tree.find_all(*_WRITE_NODES)):
            return _fail("WRITE_NOT_ALLOWED")
        if not isinstance(tree, exp.Select):
            # WITH는 Select 노드의 with 인자로 붙으므로 여기서 함께 통과함
            return _fail("NOT_SELECT")
        if any(True for _ in tree.find_all(*_UNLISTED_SYNTAX_NODES)):
            return _fail("SYNTAX_NOT_ALLOWED")
        for select in tree.find_all(exp.Select):
            if select.args.get("locks"):
                return _fail("FOR_UPDATE_NOT_ALLOWED")  # FOR UPDATE, FOR SHARE
            if select.args.get("into"):
                return _fail("SELECT_INTO_NOT_ALLOWED")

        reason = self._check_functions(tree) or self._check_tables_and_columns(tree)
        if reason:
            return _fail(reason)
        return ValidationResult(ok=True, sql=_apply_row_limit(tree).sql(dialect=DIALECT))

    @staticmethod
    def _check_functions(tree: exp.Expression) -> str | None:
        for node in tree.find_all(exp.Func):
            if isinstance(node, _OPERATOR_NODES) or isinstance(node, _CAST_NODES):
                continue
            if isinstance(node, _SET_RETURNING_NODES):
                return "FORBIDDEN_FUNCTION"
            if isinstance(node, exp.Anonymous):
                name = node.name.lower()
                if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIX):
                    return "FORBIDDEN_FUNCTION"
                return "FUNCTION_NOT_ALLOWED"
            allowed_name = _ALLOWED_FUNCTION_NODES.get(type(node))
            if allowed_name is None or allowed_name not in ALLOWED_FUNCTIONS:
                return "FUNCTION_NOT_ALLOWED"
        return None

    @staticmethod
    def _check_tables_and_columns(tree: exp.Expression) -> str | None:
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        # 별칭(테이블 별칭, 결과 컬럼 별칭, CTE 컬럼 이름)은 컬럼 이름으로 참조될 수 있어 허용 이름에 더함
        alias_names = {alias.alias.lower() for alias in tree.find_all(exp.Alias) if alias.alias}
        alias_names |= {
            column.name.lower()
            for table_alias in tree.find_all(exp.TableAlias)
            for column in table_alias.columns
        }

        qualifiers: dict[str, str | None] = {name: None for name in cte_names}  # 이름 → 허용 뷰(없으면 CTE)
        used_views: set[str] = set()
        for table in tree.find_all(exp.Table):
            schema = table.db.lower()
            name = table.name.lower()
            if table.catalog:
                return "VIEW_NOT_ALLOWED"
            if not schema and name in cte_names:
                qualifier_view = None
            else:
                if schema in FORBIDDEN_SCHEMAS:
                    return "SCHEMA_NOT_ALLOWED"
                full_name = f"{schema}.{name}"
                # 스키마 이름을 붙여 쓴 허용 뷰만 통과(31장 허용 1번)
                if schema != ALLOWED_SCHEMA or full_name not in ALLOWED_VIEWS:
                    return "VIEW_NOT_ALLOWED"
                used_views.add(full_name)
                qualifier_view = full_name
            qualifiers[name] = qualifier_view
            if table.alias:
                qualifiers[table.alias.lower()] = qualifier_view

        allowed_columns = {column for view in used_views for column in ALLOWED_VIEWS[view]}
        for column in tree.find_all(exp.Column):
            if isinstance(column.this, exp.Star):
                continue
            name = column.name.lower()
            qualifier = column.table.lower()
            if qualifier:
                if qualifier not in qualifiers:
                    return "COLUMN_NOT_ALLOWED"
                view = qualifiers[qualifier]
                if view is not None and name not in ALLOWED_VIEWS[view]:
                    return "COLUMN_NOT_ALLOWED"
                if view is None and name not in allowed_columns | alias_names:
                    return "COLUMN_NOT_ALLOWED"
            elif name not in allowed_columns | alias_names:
                return "COLUMN_NOT_ALLOWED"
        return None


def _apply_row_limit(tree: exp.Select) -> exp.Select:
    """바깥 SELECT의 LIMIT이 없으면 200을 붙이고, 200보다 크거나 숫자가 아니면 200으로 낮춤."""
    limit = tree.args.get("limit")
    value = None
    if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        value = int(limit.expression.name)
    if value is None or value > ROW_LIMIT:
        return tree.limit(ROW_LIMIT, copy=True)
    return tree


def _fail(reason: str) -> ValidationResult:
    return ValidationResult(ok=False, reason=reason)

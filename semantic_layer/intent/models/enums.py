from __future__ import annotations

from enum import Enum


INTENT_SCHEMA_VERSION = "intent-v1"


class AggregateFunction(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    MIN = "MIN"
    MAX = "MAX"


class PredicateOperator(str, Enum):
    EQ = "="
    NE = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    LIKE = "LIKE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    BETWEEN = "BETWEEN"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class LogicalOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class SortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"


class LiteralDataType(str, Enum):
    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    TIME = "TIME"
    NULL = "NULL"


class TimeRange(str, Enum):
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    THIS_WEEK = "THIS_WEEK"
    LAST_WEEK = "LAST_WEEK"
    THIS_MONTH = "THIS_MONTH"
    LAST_MONTH = "LAST_MONTH"
    THIS_QUARTER = "THIS_QUARTER"
    LAST_QUARTER = "LAST_QUARTER"
    THIS_YEAR = "THIS_YEAR"
    LAST_YEAR = "LAST_YEAR"
    DATE_RANGE = "DATE_RANGE"
    RELATIVE_DATE_RANGE = "RELATIVE_DATE_RANGE"
    YOY = "YOY"


class ComparisonType(str, Enum):
    PERIOD_OVER_PERIOD = "PERIOD_OVER_PERIOD"
    GROUP_TO_GROUP = "GROUP_TO_GROUP"
    METRIC_TO_METRIC = "METRIC_TO_METRIC"
    VALUE_TO_VALUE = "VALUE_TO_VALUE"


class ChangeType(str, Enum):
    ABSOLUTE_CHANGE = "ABSOLUTE_CHANGE"
    PERCENT_CHANGE = "PERCENT_CHANGE"
    GROWTH_RATE = "GROWTH_RATE"


class RatioOutput(str, Enum):
    RATIO = "RATIO"
    PERCENTAGE = "PERCENTAGE"


class IntentStatus(str, Enum):
    VALID = "VALID"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"


class ParserSource(str, Enum):
    RULE_ENGINE = "RULE_ENGINE"
    CLASSIFIER = "CLASSIFIER"
    LLM_FALLBACK = "LLM_FALLBACK"


class SetOperationType(str, Enum):
    UNION = "UNION"
    UNION_ALL = "UNION_ALL"
    INTERSECT = "INTERSECT"
    EXCEPT = "EXCEPT"

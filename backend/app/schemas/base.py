"""数据模型公共配置：Python 内用 snake_case，JSON 中用 camelCase。"""

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


_MESSAGES = {
    "missing": "缺少必填字段",
    "extra_forbidden": "不允许的多余字段",
    "less_than_equal": "不能大于 {le}",
    "less_than": "必须小于 {lt}",
    "greater_than_equal": "不能小于 {ge}",
    "greater_than": "必须大于 {gt}",
    "string_too_short": "长度不能少于 {min_length} 个字符",
    "string_too_long": "长度不能超过 {max_length} 个字符",
    "too_short": "至少需要 {min_length} 项",
    "too_long": "最多只能有 {max_length} 项",
    "literal_error": "取值必须是 {expected}",
    "int_type": "必须是整数",
    "int_parsing": "必须是整数",
    "string_type": "必须是字符串",
}


def format_validation_error(exc: ValidationError) -> list[str]:
    """把 Pydantic 错误转成“字段路径：中文原因”，便于定位具体字段。"""
    return format_error_list(exc.errors())


def format_error_list(errors, skip_prefix: tuple[str, ...] = ()) -> list[str]:
    lines = []
    for error in errors:
        path = ".".join(str(part) for part in error["loc"] if part not in skip_prefix) or "(整体)"
        template = _MESSAGES.get(error["type"])
        if template:
            message = template.format(**error.get("ctx", {}))
        else:
            message = str(error.get("ctx", {}).get("error") or error["msg"]).removeprefix("Value error, ")
        lines.append(f"{path}：{message}")
    return lines

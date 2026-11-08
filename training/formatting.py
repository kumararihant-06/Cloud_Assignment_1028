"""Pure helpers for building sequence-level distillation examples."""


def prompt_for(command: str) -> str:
    return f"Command: {command}\nJSON:"


def target_for(teacher_raw: str) -> str:
    return f" {teacher_raw}"


def training_text(command: str, teacher_raw: str) -> str:
    return prompt_for(command) + target_for(teacher_raw)


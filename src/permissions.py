from enum import StrEnum


class Role(StrEnum):
    BODEGA_FARMACIA = "Encargado de Bodega / Farmacia"
    JEFATURA = "Jefatura"
    REGISTRO = "Área de Registro"
    BODEGA_EXCLUIDOS = "Encargado Bodega de Excluidos"
    ADMINISTRADOR = "Administrador"


STEP_PERMISSIONS: dict[Role, set[int]] = {
    Role.BODEGA_FARMACIA: {1},
    Role.JEFATURA: {2, 5},
    Role.REGISTRO: {3, 5},
    Role.BODEGA_EXCLUIDOS: {4},
    Role.ADMINISTRADOR: {1, 2, 3, 4, 5},
}


def can_edit_step(role: str, step: int) -> bool:
    try:
        return step in STEP_PERMISSIONS[Role(role)]
    except (ValueError, KeyError):
        return False


def can_administer_users(role: str) -> bool:
    return role in {Role.JEFATURA.value, Role.ADMINISTRADOR.value}


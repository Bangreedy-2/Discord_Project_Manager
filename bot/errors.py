class OrchestratorError(Exception):
    """Base for errors whose message is safe to show to the user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CapReached(OrchestratorError):
    def __init__(self, limit: int | None = None):
        detail = f" ({limit})" if limit else ""
        super().__init__(f"You've reached the maximum number of projects{detail}.")


class DuplicateName(OrchestratorError):
    def __init__(self, name: str):
        super().__init__(f"A project named **{name}** already exists.")


class InvalidName(OrchestratorError):
    pass


class ProjectNotFound(OrchestratorError):
    def __init__(self, name: str | None = None):
        super().__init__(f"Project **{name}** not found." if name else "Project not found.")


class NotOwner(OrchestratorError):
    def __init__(self):
        super().__init__("You must be an owner of this project to do that.")


class NotCreator(OrchestratorError):
    def __init__(self):
        super().__init__("Only the project's creator or a server admin can do that.")


class NotInProject(OrchestratorError):
    def __init__(self):
        super().__init__("That channel doesn't belong to a project you manage.")


class LastOwner(OrchestratorError):
    def __init__(self):
        super().__init__("A project needs at least one owner. Promote someone else first.")


class ChannelCapReached(OrchestratorError):
    def __init__(self, limit: int):
        super().__init__(f"This project already has the maximum of {limit} channels.")


class RoleSlotsExhausted(OrchestratorError):
    def __init__(self):
        super().__init__("This server is out of role slots for new projects.")


class InvalidTarget(OrchestratorError):
    pass

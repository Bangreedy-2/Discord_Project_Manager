import discord


class ConfirmView(discord.ui.View):
    """Two-button confirmation that only the invoking user can answer."""

    def __init__(self, user_id: int, confirm_label: str = "Confirm", timeout: float = 30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.value: bool | None = None
        self.confirm.label = confirm_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who ran the command can answer this.", ephemeral=True
            )
            return False
        return True

    def _disable(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        self._disable()
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        self._disable()
        await interaction.response.edit_message(content="Cancelled.", view=self)
        self.stop()


async def confirm(
    interaction: discord.Interaction, prompt: str, confirm_label: str = "Confirm"
) -> bool:
    """Ask for confirmation in an ephemeral message. The interaction must not be responded to yet,
    or must have been deferred (then a followup is used)."""
    view = ConfirmView(interaction.user.id, confirm_label)
    if interaction.response.is_done():
        await interaction.followup.send(prompt, view=view, ephemeral=True)
    else:
        await interaction.response.send_message(prompt, view=view, ephemeral=True)
    timed_out = await view.wait()
    if timed_out:
        await interaction.edit_original_response(content="Timed out, nothing was changed.", view=None)
        return False
    return bool(view.value)

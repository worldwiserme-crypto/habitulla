"""FSM states for multi-step conversations."""
from aiogram.fsm.state import State, StatesGroup


class TrackerModes(StatesGroup):
    """Context modes activated by main menu buttons.

    When user is in habit_mode, all text/voice is parsed as habit (bias the AI).
    Same for budget_mode. No mode = auto-detect (default).
    """
    habit_mode = State()
    budget_mode = State()


class SubscriptionStates(StatesGroup):
    """User subscribing flow."""
    waiting_plan_selection = State()
    waiting_receipt = State()


class AdminStates(StatesGroup):
    """Admin panel flows."""
    waiting_broadcast_text = State()
    confirming_broadcast = State()
    waiting_user_id_lookup = State()
    waiting_rejection_reason = State()


class SettingsStates(StatesGroup):
    waiting_currency_choice = State()


class ReportStates(StatesGroup):
    waiting_custom_dates = State()


class ResetStates(StatesGroup):
    waiting_confirm = State()

# tests/test_injector.py
from unittest.mock import patch, MagicMock, call


def test_clipboard_path_used_by_default(mocker):
    mock_paste = mocker.patch("pyperclip.paste", return_value="previous")
    mock_copy = mocker.patch("pyperclip.copy")
    mock_send = mocker.patch("keyboard.send")
    mocker.patch("time.sleep")

    from app.engine.injector import inject
    inject("hello")

    mock_copy.assert_any_call("hello")
    mock_send.assert_called_once_with("ctrl+v")


def test_previous_clipboard_restored(mocker):
    mocker.patch("pyperclip.paste", return_value="old content")
    mock_copy = mocker.patch("pyperclip.copy")
    mocker.patch("keyboard.send")
    mocker.patch("time.sleep")

    from app.engine.injector import inject
    inject("new text")

    calls = mock_copy.call_args_list
    assert calls[-1] == call("old content")


def test_fallback_keyboard_type_on_pyperclip_exception(mocker):
    mocker.patch("pyperclip.paste", side_effect=Exception("no clipboard"))
    mock_type = mocker.patch("keyboard.type")

    from app.engine.injector import inject
    inject("fallback text")

    mock_type.assert_called_once_with("fallback text")


def test_fallback_on_copy_exception(mocker):
    mocker.patch("pyperclip.paste", return_value="x")
    mocker.patch("pyperclip.copy", side_effect=Exception("clipboard error"))
    mock_type = mocker.patch("keyboard.type")

    from app.engine.injector import inject
    inject("text")

    mock_type.assert_called_once_with("text")

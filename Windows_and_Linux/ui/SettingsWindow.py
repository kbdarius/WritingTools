import os
import json
import sys
import threading
import webbrowser

from aiprovider import AIProvider, NoWheelComboBox
from azure_speech import AzureSpeechService
from azure_usage import (
    AZURE_CLI_INSTALL_URL,
    AZURE_POWERSHELL_INSTALL_URL,
    install_azure_cli as install_azure_cli_tool,
    install_azure_powershell as install_azure_powershell_tool,
    azure_cli_path,
    azure_powershell_available,
    get_speech_usage,
)
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QRadioButton, QScrollArea

from ui.AutostartManager import AutostartManager
from ui.CustomPopupWindow import (
    CustomPopupWindow,
    PinnedTextEditorDialog,
    PinnedTextTreeWidget,
    PopupButtonVisibilityDialog,
)
from ui.UIUtils import UIUtils, colorMode

_ = lambda x: x


class PinnedTextSettingsPanel(QtWidgets.QWidget):
    """Embedded pinned-text manager used as a reliable Settings fallback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = CustomPopupWindow.load_pinned_texts()

        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            _("Manage reusable text snippets here. Categories are shown before their items.")
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.list_widget = PinnedTextTreeWidget()
        self.list_widget.setHeaderHidden(True)
        self.list_widget.setMinimumHeight(230)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.list_widget.setDragDropOverwriteMode(False)
        layout.addWidget(self.list_widget, 1)

        self.preview = QtWidgets.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(_("Select an item to preview it here."))
        self.preview.setMaximumHeight(110)
        self.list_widget.currentItemChanged.connect(self._update_preview)
        self.list_widget.items_reordered.connect(self._save_tree_order)
        layout.addWidget(self.preview)

        buttons = QtWidgets.QHBoxLayout()
        for label, handler in (
            (_("Add"), self._add),
            (_("Edit"), self._edit),
            (_("Delete"), self._delete),
            (_("Export"), self._export),
            (_("Import"), self._import),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self, selected=None):
        self.list_widget.clear()
        groups = {}
        for entry in self.entries:
            text = " ".join((entry.get("text") or "").split())
            label = (entry.get("label") or "").strip() or text[:60] or _("(blank)")
            group = str(entry.get("group") or "").strip()
            if group:
                if group not in groups:
                    groups[group] = QtWidgets.QTreeWidgetItem([group])
                    groups[group].setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, group)
                    groups[group].setFlags(
                        QtCore.Qt.ItemFlag.ItemIsEnabled
                        | QtCore.Qt.ItemFlag.ItemIsSelectable
                        | QtCore.Qt.ItemFlag.ItemIsDragEnabled
                        | QtCore.Qt.ItemFlag.ItemIsDropEnabled
                    )
                    self.list_widget.addTopLevelItem(groups[group])
                    groups[group].setExpanded(True)
                item = QtWidgets.QTreeWidgetItem([label])
                groups[group].addChild(item)
            else:
                item = QtWidgets.QTreeWidgetItem([label])
                self.list_widget.addTopLevelItem(item)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, entry)
            item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsSelectable
                | QtCore.Qt.ItemFlag.ItemIsDragEnabled
            )
        if selected:
            iterator = QtWidgets.QTreeWidgetItemIterator(self.list_widget)
            while iterator.value():
                item = iterator.value()
                if item.data(0, QtCore.Qt.ItemDataRole.UserRole) == selected:
                    self.list_widget.setCurrentItem(item)
                    break
                iterator += 1

    def _save_tree_order(self):
        ordered = []
        for index in range(self.list_widget.topLevelItemCount()):
            parent = self.list_widget.topLevelItem(index)
            if parent.childCount():
                group = parent.data(0, QtCore.Qt.ItemDataRole.UserRole + 1) or parent.text(0)
                for child_index in range(parent.childCount()):
                    entry = parent.child(child_index).data(0, QtCore.Qt.ItemDataRole.UserRole)
                    if isinstance(entry, dict):
                        entry["group"] = str(group)
                        ordered.append(entry)
            else:
                entry = parent.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(entry, dict):
                    entry["group"] = ""
                    ordered.append(entry)
        if ordered:
            self.entries = ordered
            CustomPopupWindow.save_pinned_texts(self.entries)

    def _selected(self):
        item = self.list_widget.currentItem()
        entry = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not isinstance(entry, dict):
            return None, None
        index = next((i for i, value in enumerate(self.entries) if value == entry), -1)
        return index, entry

    def _update_preview(self, item, _previous=None):
        entry = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None
        self.preview.setPlainText(entry.get("text", "") if isinstance(entry, dict) else "")

    def _edit_entry(self, entry, index=None):
        dialog = PinnedTextEditorDialog(self, entry, _("Edit Pinned Text") if index is not None else _("Add Pinned Text"))
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        text, label, group = dialog.values()
        if not text.strip():
            QtWidgets.QMessageBox.information(self, _("Pinned Text"), _("Text cannot be blank."))
            return
        if index is None:
            self.entries.insert(0, {
                "text": text.strip(), "label": label, "group": group,
                "source": "manual",
                "created_at": QtCore.QDateTime.currentDateTimeUtc().toString(QtCore.Qt.DateFormat.ISODate),
            })
            selected = self.entries[0]
        else:
            self.entries[index].update({"text": text.strip(), "label": label, "group": group})
            selected = self.entries[index]
        CustomPopupWindow.save_pinned_texts(self.entries)
        self._refresh(selected)

    def _add(self):
        self._edit_entry({"source": "manual"})

    def _edit(self):
        index, entry = self._selected()
        if entry:
            self._edit_entry(entry.copy(), index)

    def _delete(self):
        index, entry = self._selected()
        if entry and QtWidgets.QMessageBox.question(self, _("Delete pinned text"), _("Delete the selected item?")) == QtWidgets.QMessageBox.StandardButton.Yes:
            del self.entries[index]
            CustomPopupWindow.save_pinned_texts(self.entries)
            self._refresh()

    def _export(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, _("Export pinned text"), "pinned-texts.json", "JSON files (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.entries, handle, indent=2, ensure_ascii=False)

    def _import(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, _("Import pinned text"), "", "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                entries = json.load(handle)
            if not isinstance(entries, list) or not all(isinstance(item, dict) and item.get("text") for item in entries):
                raise ValueError(_("This file is not a valid pinned text export."))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QtWidgets.QMessageBox.warning(self, _("Import failed"), str(exc))
            return
        self.entries = entries
        CustomPopupWindow.save_pinned_texts(self.entries)
        self._refresh()

class SettingsWindow(QtWidgets.QWidget):
    """
    The settings window for the application.
    Now with scrolling support for better usability on smaller screens.
    """
    close_signal = QtCore.Signal()
    validation_finished = QtCore.Signal(bool, str)
    azure_test_finished = QtCore.Signal(bool, str)
    azure_usage_finished = QtCore.Signal(bool, str)
    azure_install_finished = QtCore.Signal(str, bool, str)

    def __init__(self, app, providers_only=False):
        super().__init__()
        self.app = app
        self.current_provider_layout = None
        self.providers_only = providers_only
        self.gradient_radio = None
        self.plain_radio = None
        self.provider_dropdown = None
        self.provider_container = None
        self.autostart_checkbox = None
        self.shortcut_input = None
        self.custom_prompt_checkbox = None
        self.review_before_insert_checkbox = None
        self.read_aloud_provider_dropdown = None
        self.azure_speech_key_input = None
        self.azure_speech_region_input = None
        self.azure_voice_dropdown = None
        self.natural_reading_checkbox = None
        self.azure_test_button = None
        self.azure_usage_button = None
        self.azure_usage_label = None
        self.azure_cli_status_label = None
        self.azure_cli_install_button = None
        self.azure_powershell_install_button = None
        self.option_prompt_inputs = {}
        self.save_button = None
        self.validation_label = None
        self._validation_in_progress = False
        self._pending_provider = None
        self._pending_provider_config = None
        self._provider_drafts = {}
        self._active_provider_index = None
        self._azure_install_in_progress = False
        self.settings_tabs = None
        self.pinned_text_panel = None
        self.pinned_text_page = None
        self.init_ui()
        self.validation_finished.connect(self._finish_provider_validation)
        self.azure_test_finished.connect(self._finish_azure_speech_test)
        self.azure_usage_finished.connect(self._finish_azure_usage_check)
        self.azure_install_finished.connect(self._finish_azure_install)
        self.retranslate_ui()


    def retranslate_ui(self):
        self.setWindowTitle(_("Settings"))

    def init_provider_ui(self, provider: AIProvider, layout):
        """
        Initialize the user interface for the provider, including logo, name, description and all settings.
        """
        if self.current_provider_layout:
            self.current_provider_layout.setParent(None)
            UIUtils.clear_layout(self.current_provider_layout)
            self.current_provider_layout.deleteLater()

        self.current_provider_layout = QtWidgets.QVBoxLayout()

        # Create a horizontal layout for the logo and provider name
        provider_header_layout = QtWidgets.QHBoxLayout()
        provider_header_layout.setSpacing(10)
        provider_header_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        if provider.logo:
            logo_path = os.path.join(os.path.dirname(sys.argv[0]), 'icons', f"provider_{provider.logo}.png")
            if os.path.exists(logo_path):
                targetPixmap = UIUtils.resize_and_round_image(QImage(logo_path), 30, 15)
                logo_label = QtWidgets.QLabel()
                logo_label.setPixmap(targetPixmap)
                logo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
                provider_header_layout.addWidget(logo_label)

        provider_name_label = QtWidgets.QLabel(provider.provider_name)
        provider_name_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
        provider_name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
        provider_header_layout.addWidget(provider_name_label)

        self.current_provider_layout.addLayout(provider_header_layout)

        if provider.description:
            description_label = QtWidgets.QLabel(provider.description)
            description_label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'}; text-align: center;")
            description_label.setWordWrap(True)
            self.current_provider_layout.addWidget(description_label)

        if hasattr(provider, 'ollama_button_text'):
            # Create container for buttons
            button_layout = QtWidgets.QHBoxLayout()
            
            # Add Ollama setup button
            ollama_button = QtWidgets.QPushButton(provider.ollama_button_text)
            ollama_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#4CAF50' if colorMode == 'dark' else '#008CBA'};
                    color: white;
                    padding: 10px;
                    font-size: 16px;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: {'#45a049' if colorMode == 'dark' else '#007095'};
                }}
            """)
            ollama_button.clicked.connect(provider.ollama_button_action)
            button_layout.addWidget(ollama_button)
            
            # Add original button
            main_button = QtWidgets.QPushButton(provider.button_text)
            main_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#4CAF50' if colorMode == 'dark' else '#008CBA'};
                    color: white;
                    padding: 10px;
                    font-size: 16px;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: {'#45a049' if colorMode == 'dark' else '#007095'};
                }}
            """)
            main_button.clicked.connect(provider.button_action)
            button_layout.addWidget(main_button)
            
            self.current_provider_layout.addLayout(button_layout)
        else:
            # Original single button logic
            if provider.button_text:
                button = QtWidgets.QPushButton(provider.button_text)
                button.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {'#4CAF50' if colorMode == 'dark' else '#008CBA'};
                        color: white;
                        padding: 10px;
                        font-size: 16px;
                        border: none;
                        border-radius: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {'#45a049' if colorMode == 'dark' else '#007095'};
                    }}
                """)
                button.clicked.connect(provider.button_action)
                self.current_provider_layout.addWidget(button, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        # Initialize config if needed
        if "providers" not in self.app.config:
            self.app.config["providers"] = {}
        if provider.provider_name not in self.app.config["providers"]:
            self.app.config["providers"][provider.provider_name] = {}

        provider_config = self._provider_drafts.get(
            provider.provider_name,
            self.app.config["providers"][provider.provider_name],
        )

        # Add provider settings
        for setting in provider.settings:
            setting.set_value(provider_config.get(setting.name, setting.default_value))
            setting.render_to_layout(self.current_provider_layout)

        layout.addLayout(self.current_provider_layout)

    def init_ui(self):
        """
        Initialize the user interface for the settings window.
        Now includes a scroll area for better handling of content on smaller screens.
        """
        self.setWindowTitle(_('Settings'))
        # Set the exact width we want (592px) as both minimum and default
        self.setMinimumWidth(592)
        self.setFixedWidth(592)  # This makes the width non-resizable
        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {'#555' if colorMode == 'dark' else '#d0d5dd'};
                border-radius: 12px;
                background: {'rgba(30,30,30,0.72)' if colorMode == 'dark' else 'rgba(255,255,255,0.82)'};
            }}
            QTabBar::tab {{
                background: {'#303030' if colorMode == 'dark' else '#e8edf3'};
                color: {'#d8d8d8' if colorMode == 'dark' else '#344054'};
                padding: 10px 18px;
                margin-right: 3px;
                border-radius: 8px 8px 0 0;
            }}
            QTabBar::tab:selected {{
                background: {'#4b77a5' if colorMode == 'dark' else '#ffffff'};
                color: {'#ffffff' if colorMode == 'dark' else '#1d2939'};
                font-weight: bold;
            }}
            QScrollArea {{ border: none; background: transparent; }}
            QLineEdit, QPlainTextEdit, QComboBox {{
                border: 1px solid {'#626262' if colorMode == 'dark' else '#c6cbd3'};
                border-radius: 7px;
                padding: 7px;
            }}
            QCheckBox {{ spacing: 8px; }}
            QPushButton {{ min-height: 30px; }}
        """)

        # Set up the main window layout with spacing for bottom elements
        UIUtils.setup_window_and_layout(self)
        main_layout = QtWidgets.QVBoxLayout(self.background)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)  # Add spacing between scroll area and bottom elements

        scroll_style = """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(128, 128, 128, 0.5);
                min-height: 20px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """

        def create_scroll_page():
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setStyleSheet(scroll_style)
            content = QtWidgets.QWidget()
            content.setStyleSheet(
                f"background: {'rgba(18,18,18,0.32)' if colorMode == 'dark' else 'rgba(248,250,252,0.62)'};"
                "border-radius: 10px;"
            )
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(26, 24, 26, 28)
            layout.setSpacing(14)
            scroll.setWidget(content)
            return scroll, layout

        tabs = QtWidgets.QTabWidget()
        self.settings_tabs = tabs
        tabs.setDocumentMode(True)
        general_page, general_layout = create_scroll_page()
        prompts_page, prompts_layout = create_scroll_page()
        ai_page, ai_layout = create_scroll_page()
        pinned_page, pinned_layout = create_scroll_page()
        self.pinned_text_page = pinned_page
        if not self.providers_only:
            tabs.addTab(general_page, _("General"))
            tabs.addTab(prompts_page, _("Prompts"))
            tabs.addTab(pinned_page, _("Pinned Text"))
        tabs.addTab(ai_page, _("AI Provider"))
        main_layout.addWidget(tabs)

        content_layout = general_layout

        if not self.providers_only:
            self.pinned_text_panel = PinnedTextSettingsPanel(self)
            pinned_layout.addWidget(self.pinned_text_panel)

        if not self.providers_only:
            title_label = QtWidgets.QLabel(_("Settings"))
            title_label.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
            content_layout.addWidget(title_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

            # Add autostart checkbox for Windows compiled version
            if AutostartManager.get_startup_path():
                self.autostart_checkbox = QtWidgets.QCheckBox(_("Start on Boot"))
                self.autostart_checkbox.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
                self.autostart_checkbox.setChecked(AutostartManager.check_autostart())
                self.autostart_checkbox.stateChanged.connect(self.toggle_autostart)
                content_layout.addWidget(self.autostart_checkbox)

            # Add shortcut key input
            shortcut_label = QtWidgets.QLabel(_("Shortcut Key:"))
            shortcut_label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
            content_layout.addWidget(shortcut_label)

            self.shortcut_input = QtWidgets.QLineEdit(self.app.config.get('shortcut', 'ctrl+space'))
            self.shortcut_input.setStyleSheet(f"""
                font-size: 16px;
                padding: 5px;
                background-color: {'#444' if colorMode == 'dark' else 'white'};
                color: {'#ffffff' if colorMode == 'dark' else '#000000'};
                border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
            """)
            content_layout.addWidget(self.shortcut_input)

            button_visibility_button = QtWidgets.QPushButton(
                "Choose Ctrl+Space Buttons..."
            )
            button_visibility_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {'#444' if colorMode == 'dark' else '#f0f0f0'};
                    color: {'#ffffff' if colorMode == 'dark' else '#000000'};
                    border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
                    border-radius: 5px;
                    padding: 8px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background-color: {'#555' if colorMode == 'dark' else '#e0e0e0'};
                }}
            """)
            button_visibility_button.clicked.connect(self.show_button_visibility_dialog)
            content_layout.addWidget(button_visibility_button)

            fast_track_label = QtWidgets.QLabel(_("Ctrl+Space fast track:"))
            content_layout.addWidget(fast_track_label)
            self.fast_track_dropdown = NoWheelComboBox()
            self.fast_track_dropdown.addItem(_("Off"), "")
            for name, config in (self.app.options or {}).items():
                if config.get('visible', True):
                    self.fast_track_dropdown.addItem(name, name)
            fast_track = self.app.config.get('fast_track_action', '')
            fast_index = self.fast_track_dropdown.findData(fast_track)
            self.fast_track_dropdown.setCurrentIndex(max(0, fast_index))
            self.fast_track_dropdown.setToolTip(
                _("Choose one visible action to run automatically when Ctrl+Space is pressed.")
            )
            content_layout.addWidget(self.fast_track_dropdown)

            self.review_before_insert_checkbox = QtWidgets.QCheckBox(
                "Review results before inserting"
            )
            self.review_before_insert_checkbox.setToolTip(
                "Show every result in a window. Use Insert at cursor only after reviewing it."
            )
            self.review_before_insert_checkbox.setChecked(
                self.app.config.get('review_before_insert', True)
            )
            self.review_before_insert_checkbox.setStyleSheet(
                f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
            )
            content_layout.addWidget(self.review_before_insert_checkbox)

            transfer_label = QtWidgets.QLabel(_("Move settings to another PC"))
            transfer_label.setStyleSheet(
                f"font-size: 17px; font-weight: bold; margin-top: 12px; "
                f"color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
            )
            content_layout.addWidget(transfer_label)
            transfer_help = QtWidgets.QLabel(
                _("Export your settings and prompt buttons to one JSON file, then import it on the other PC. "
                  "The file can contain API keys, so keep it private.")
            )
            transfer_help.setWordWrap(True)
            transfer_help.setStyleSheet(
                f"font-size: 13px; color: {'#cccccc' if colorMode == 'dark' else '#667085'};"
            )
            content_layout.addWidget(transfer_help)
            transfer_buttons = QHBoxLayout()
            export_button = QtWidgets.QPushButton(_("Export settings"))
            import_button = QtWidgets.QPushButton(_("Import settings"))
            export_button.clicked.connect(self.export_settings)
            import_button.clicked.connect(self.import_settings)
            transfer_buttons.addWidget(export_button)
            transfer_buttons.addWidget(import_button)
            content_layout.addLayout(transfer_buttons)

            self.custom_prompt_checkbox = QtWidgets.QCheckBox(
                _("Show custom prompt box in popup")
            )
            self.custom_prompt_checkbox.setToolTip(
                _("Most people only use the monitor buttons. Turn this on if you want a small text box for extra instructions.")
            )
            self.custom_prompt_checkbox.setChecked(
                self.app.config.get('show_custom_prompt_box', False)
            )
            self.custom_prompt_checkbox.setStyleSheet(
                f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
            )
            content_layout.addWidget(self.custom_prompt_checkbox)

            # Prompt management lives on its own tab.
            content_layout = prompts_layout
            ai_prompt_label = QtWidgets.QLabel(_("AI Button Prompts"))
            ai_prompt_label.setStyleSheet(
                f"font-size: 18px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
            )
            content_layout.addWidget(ai_prompt_label)
            prompt_intro = QtWidgets.QLabel(
                _("Edit the prefix and system instruction for each button below. "
                  "These are sent to your selected AI provider with the highlighted text.")
            )
            prompt_intro.setStyleSheet(
                f"font-size: 14px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
            )
            prompt_intro.setWordWrap(True)
            content_layout.addWidget(prompt_intro)

            for option_name, option_config in (self.app.options or {}).items():
                if option_config.get("action") == "read_aloud":
                    continue
                if "instruction" not in option_config and "prefix" not in option_config:
                    continue

                section = QtWidgets.QFrame()
                section.setStyleSheet(
                    f"border: 1px solid {'#444' if colorMode == 'dark' else '#ccc'}; "
                    "border-radius: 8px; padding: 8px;"
                )
                section_layout = QtWidgets.QVBoxLayout(section)
                section_layout.setSpacing(8)

                name_row = QtWidgets.QHBoxLayout()
                name_input = QtWidgets.QLineEdit(option_name)
                name_input.setPlaceholderText(_("Prompt name"))
                name_input.setStyleSheet(
                    f"font-size: 16px; font-weight: bold; background-color: {'#444' if colorMode == 'dark' else 'white'}; "
                    f"color: {'#ffffff' if colorMode == 'dark' else '#000000'}; border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};"
                )
                name_row.addWidget(name_input)
                visible_checkbox = QtWidgets.QCheckBox(_("Show in Ctrl+Space"))
                visible_checkbox.setChecked(option_config.get("visible", True))
                visible_checkbox.setToolTip(
                    _("Unchecked prompts stay saved here, but they are hidden from the Ctrl+Space popup.")
                )
                visible_checkbox.setStyleSheet(
                    f"font-size: 14px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
                )
                name_row.addWidget(visible_checkbox)
                delete_button = QtWidgets.QPushButton(_("Delete"))
                delete_button.setStyleSheet(
                    "QPushButton { background-color: #b3261e; color: white; border: none; "
                    "border-radius: 5px; padding: 7px 12px; } "
                    "QPushButton:hover { background-color: #8c1d18; }"
                )
                delete_button.clicked.connect(
                    lambda _checked=False, name=option_name: self.mark_prompt_deleted(name)
                )
                name_row.addWidget(delete_button)
                section_layout.addLayout(name_row)

                prefix_label = QtWidgets.QLabel(_("Prefix"))
                prefix_label.setStyleSheet(
                    f"font-size: 14px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
                )
                section_layout.addWidget(prefix_label)
                prefix_input = QtWidgets.QLineEdit(option_config.get("prefix", ""))
                prefix_input.setStyleSheet(
                    f"font-size: 14px; background-color: {'#444' if colorMode == 'dark' else 'white'}; "
                    f"color: {'#ffffff' if colorMode == 'dark' else '#000000'}; border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};"
                )
                section_layout.addWidget(prefix_input)

                instruction_label = QtWidgets.QLabel(_("System Instruction"))
                instruction_label.setStyleSheet(
                    f"font-size: 14px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
                )
                section_layout.addWidget(instruction_label)
                instruction_input = QtWidgets.QPlainTextEdit(option_config.get("instruction", ""))
                instruction_input.setStyleSheet(
                    f"font-size: 14px; background-color: {'#333' if colorMode == 'dark' else 'white'}; "
                    f"color: {'#ffffff' if colorMode == 'dark' else '#000000'}; border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};"
                )
                instruction_input.setMinimumHeight(120)
                section_layout.addWidget(instruction_input)

                self.option_prompt_inputs[option_name] = {
                    "name": name_input,
                    "visible": visible_checkbox,
                    "prefix": prefix_input,
                    "instruction": instruction_input,
                    "section": section,
                    "deleted": False,
                }
                content_layout.addWidget(section)

            # Return to the General tab for appearance controls.
            content_layout = general_layout
            # Add theme selection
            theme_label = QtWidgets.QLabel(_("Background Theme:"))
            theme_label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
            content_layout.addWidget(theme_label)

            theme_layout = QHBoxLayout()
            self.gradient_radio = QRadioButton(_("Blurry Gradient"))
            self.plain_radio = QRadioButton(_("Plain"))
            self.gradient_radio.setStyleSheet(f"color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
            self.plain_radio.setStyleSheet(f"color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
            current_theme = self.app.config.get('theme', 'gradient')
            self.gradient_radio.setChecked(current_theme == 'gradient')
            self.plain_radio.setChecked(current_theme == 'plain')
            theme_layout.addWidget(self.gradient_radio)
            theme_layout.addWidget(self.plain_radio)
            content_layout.addLayout(theme_layout)

        # Provider controls live on the AI Provider tab.
        content_layout = ai_layout
        ai_cards_layout = ai_layout
        provider_title = QtWidgets.QLabel(_("AI and speech setup"))
        provider_title.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {'#ffffff' if colorMode == 'dark' else '#182230'};"
        )
        content_layout.addWidget(provider_title)
        provider_subtitle = QtWidgets.QLabel(
            _("Choose the AI that writes for you, then configure the voice that reads text aloud.")
        )
        provider_subtitle.setWordWrap(True)
        provider_subtitle.setStyleSheet(
            f"font-size: 14px; color: {'#c7cbd1' if colorMode == 'dark' else '#667085'};"
        )
        content_layout.addWidget(provider_subtitle)

        def create_provider_card():
            card = QtWidgets.QFrame()
            card.setObjectName("providerCard")
            card.setStyleSheet(f"""
                QFrame#providerCard {{
                    background: {'rgba(42, 42, 42, 0.78)' if colorMode == 'dark' else 'rgba(255, 255, 255, 0.93)'};
                    border: 1px solid {'#5c6570' if colorMode == 'dark' else '#d8dee8'};
                    border-radius: 12px;
                }}
            """)
            layout = QtWidgets.QVBoxLayout(card)
            layout.setContentsMargins(18, 16, 18, 18)
            layout.setSpacing(10)
            ai_cards_layout.addWidget(card)
            return layout

        speech_layout = create_provider_card()
        content_layout = speech_layout
        read_aloud_label = QtWidgets.QLabel(_("Read Aloud"))
        read_aloud_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(read_aloud_label)

        read_aloud_intro = QtWidgets.QLabel(
            _("Configure the voice provider used for Read Aloud and its speech credentials.")
        )
        read_aloud_intro.setWordWrap(True)
        read_aloud_intro.setStyleSheet(
            f"font-size: 14px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(read_aloud_intro)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QtWidgets.QLabel(_("Reading speed:")))
        self.read_aloud_speed_dropdown = NoWheelComboBox()
        for rate in (0.75, 1.0, 1.25, 1.5, 2.0):
            self.read_aloud_speed_dropdown.addItem(f"{rate:g}x", rate)
        saved_rate = float(self.app.config.get('read_aloud_rate', 1.0))
        self.read_aloud_speed_dropdown.setCurrentIndex(max(0, self.read_aloud_speed_dropdown.findData(saved_rate)))
        speed_row.addWidget(self.read_aloud_speed_dropdown)
        content_layout.addLayout(speed_row)

        azure_settings = self.app.config.get('azure_speech', {})

        self.natural_reading_checkbox = QtWidgets.QCheckBox(
            _("Natural reading mode (skip URLs, code, and machine-style identifiers)")
        )
        self.natural_reading_checkbox.setChecked(
            azure_settings.get('natural_reading', True)
        )
        self.natural_reading_checkbox.setToolTip(
            _("Shorten filenames and technical fragments before sending text to Azure Speech.")
        )
        self.natural_reading_checkbox.setStyleSheet(
            f"font-size: 14px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(self.natural_reading_checkbox)

        self.read_aloud_provider_dropdown = NoWheelComboBox()
        self.read_aloud_provider_dropdown.addItem(_("Microsoft Azure Speech"), "azure")
        self.read_aloud_provider_dropdown.setToolTip(
            _("Azure Speech is temporarily the only available Read Aloud provider.")
        )
        self.read_aloud_provider_dropdown.setStyleSheet(f"""
            font-size: 16px;
            padding: 5px;
            background-color: {'#444' if colorMode == 'dark' else 'white'};
            color: {'#ffffff' if colorMode == 'dark' else '#000000'};
            border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
        """)
        content_layout.addWidget(self.read_aloud_provider_dropdown)

        azure_key_label = QtWidgets.QLabel(_("Azure Speech resource key:"))
        azure_key_label.setStyleSheet(
            f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(azure_key_label)
        self.azure_speech_key_input = QtWidgets.QLineEdit(azure_settings.get('key', ''))
        self.azure_speech_key_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.azure_speech_key_input.setPlaceholderText(_("Paste the key from your Azure Speech resource"))
        content_layout.addWidget(self.azure_speech_key_input)

        azure_key_note = QtWidgets.QLabel(
            _("This Speech key is separate from the Foundry / Azure OpenAI key used by Writing AI.")
        )
        azure_key_note.setWordWrap(True)
        azure_key_note.setStyleSheet(
            f"font-size: 13px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(azure_key_note)

        azure_region_label = QtWidgets.QLabel(_("Azure Speech region:"))
        azure_region_label.setStyleSheet(
            f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(azure_region_label)
        self.azure_speech_region_input = QtWidgets.QLineEdit(
            azure_settings.get('region', 'eastus')
        )
        self.azure_speech_region_input.setPlaceholderText(_("For example: eastus"))
        content_layout.addWidget(self.azure_speech_region_input)

        azure_voice_label = QtWidgets.QLabel(_("English Read Aloud voice:"))
        azure_voice_label.setStyleSheet(
            f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(azure_voice_label)
        self.azure_voice_dropdown = NoWheelComboBox()
        for voice_name, voice_id in AzureSpeechService.ENGLISH_VOICES:
            self.azure_voice_dropdown.addItem(voice_name, voice_id)
        saved_voice = AzureSpeechService._normalize_english_voice(
            azure_settings.get('voice')
        )
        saved_voice_index = self.azure_voice_dropdown.findData(saved_voice)
        self.azure_voice_dropdown.setCurrentIndex(max(0, saved_voice_index))
        self.azure_voice_dropdown.setToolTip(
            _("Choose the Azure voice used for English. Persian text still uses Dilara automatically.")
        )
        self.azure_voice_dropdown.setStyleSheet(f"""
            font-size: 16px;
            padding: 5px;
            background-color: {'#444' if colorMode == 'dark' else 'white'};
            color: {'#ffffff' if colorMode == 'dark' else '#000000'};
            border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
        """)
        content_layout.addWidget(self.azure_voice_dropdown)

        persian_voice_note = QtWidgets.QLabel(
            _("Persian/Farsi text automatically uses Dilara; this English selection does not replace it.")
        )
        persian_voice_note.setWordWrap(True)
        persian_voice_note.setStyleSheet(
            f"font-size: 13px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(persian_voice_note)

        self.azure_test_button = QtWidgets.QPushButton(_("\u25b6  Test selected voice"))
        self.azure_test_button.setToolTip(
            _("Connect to Azure and play a short sample of the highlighted English voice.")
        )
        self.azure_test_button.clicked.connect(self.test_azure_speech)
        content_layout.addWidget(self.azure_test_button)

        azure_usage_title = QtWidgets.QLabel(_("Azure usage and free quota:"))
        azure_usage_title.setStyleSheet(
            f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(azure_usage_title)
        self.azure_usage_label = QtWidgets.QLabel(
            _("Click Check Azure usage to retrieve the current month from Azure Monitor.")
        )
        self.azure_usage_label.setWordWrap(True)
        self.azure_usage_label.setStyleSheet(
            f"font-size: 13px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(self.azure_usage_label)
        if self.azure_usage_button is None:
            self.azure_usage_button = QtWidgets.QPushButton(_("↻  Check Azure usage"))
        self.azure_usage_button.setToolTip(
            _("Read the official Synthesized Characters metric for this month.")
        )
        self.azure_usage_button.clicked.connect(self.check_azure_usage)
        self.azure_usage_button.setText(_("Check Azure usage"))
        content_layout.addWidget(self.azure_usage_button)

        cli_available = bool(azure_cli_path())
        powershell_available = azure_powershell_available()
        cli_status = _("Azure CLI detected.") if cli_available else _("Azure CLI is not installed.")
        powershell_status = (
            _("Azure PowerShell detected.") if powershell_available
            else _("Azure PowerShell is not installed (optional).")
        )
        self.azure_cli_status_label = QtWidgets.QLabel(f"{cli_status} {powershell_status}")
        self.azure_cli_status_label.setWordWrap(True)
        self.azure_cli_status_label.setStyleSheet(
            f"font-size: 13px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(self.azure_cli_status_label)
        if not cli_available:
            self.azure_cli_install_button = QtWidgets.QPushButton(_("Install Azure CLI (Microsoft)"))
            self.azure_cli_install_button.clicked.connect(self.install_azure_cli)
            content_layout.addWidget(self.azure_cli_install_button)
        if not powershell_available:
            self.azure_powershell_install_button = QtWidgets.QPushButton(
                _("Install Azure PowerShell (Microsoft)")
            )
            self.azure_powershell_install_button.clicked.connect(
                self.install_azure_powershell
            )
            content_layout.addWidget(self.azure_powershell_install_button)

        writing_layout = create_provider_card()
        content_layout = writing_layout
        writing_label = QtWidgets.QLabel(_("Writing AI"))
        writing_label.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(writing_label)
        writing_intro = QtWidgets.QLabel(
            _("This provider handles Rewrite, prompts, and follow-up requests. Select one, then enter only the credentials it needs.")
        )
        writing_intro.setWordWrap(True)
        writing_intro.setStyleSheet(
            f"font-size: 14px; color: {'#cccccc' if colorMode == 'dark' else '#555555'};"
        )
        content_layout.addWidget(writing_intro)

        # Add provider selection
        provider_label = QtWidgets.QLabel(_("Writing AI provider:"))
        provider_label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
        content_layout.addWidget(provider_label)

        self.provider_dropdown = NoWheelComboBox()
        self.provider_dropdown.setStyleSheet(f"""
            font-size: 16px;
            padding: 5px;
            background-color: {'#444' if colorMode == 'dark' else 'white'};
            color: {'#ffffff' if colorMode == 'dark' else '#000000'};
            border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
        """)
        self.provider_dropdown.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.provider_dropdown.setToolTip(
            _(
                "Gemini is the simplest option for regular PCs. Azure OpenAI is for work or "
                "restricted PCs. OpenAI Compatible is for advanced custom services."
            )
        )

        current_provider = self.app.config.get('provider', self.app.providers[0].provider_name)
        for provider in self.app.providers:
            self.provider_dropdown.addItem(provider.provider_name)
        current_provider_index = self.provider_dropdown.findText(current_provider)
        self.provider_dropdown.setCurrentIndex(max(0, current_provider_index))
        content_layout.addWidget(self.provider_dropdown)

        # Create container for provider UI
        self.provider_container = QtWidgets.QVBoxLayout()
        self.provider_container.setSpacing(10)
        content_layout.addLayout(self.provider_container)

        # Initialize provider UI
        provider_instance = self.app.providers[self.provider_dropdown.currentIndex()]
        self.init_provider_ui(provider_instance, self.provider_container)
        self._active_provider_index = self.provider_dropdown.currentIndex()
        self._initial_provider_state = (
            self.provider_dropdown.currentText(),
            provider_instance.get_pending_config().copy(),
        )

        # Connect provider dropdown
        self.provider_dropdown.currentIndexChanged.connect(
            self._provider_selection_changed
        )

        test_button = QtWidgets.QPushButton(_("Test writing AI connection"))
        test_button.setToolTip(_("Verify that the selected credentials can reach the selected model."))
        test_button.clicked.connect(self.test_provider_connection)
        content_layout.addWidget(test_button)

        # Create bottom container for save button and restart notice
        bottom_container = QtWidgets.QWidget()
        bottom_container.setStyleSheet("background: transparent;")  # Ensure transparency
        bottom_layout = QtWidgets.QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(30, 0, 30, 30)  # Match content margins except top
        bottom_layout.setSpacing(10)

        # Add save button to bottom container
        self.save_button = QtWidgets.QPushButton(_("Finish AI Setup") if self.providers_only else _("Save"))
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 16px;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.save_button.clicked.connect(self.save_settings)
        bottom_layout.addWidget(self.save_button)

        self.validation_label = QtWidgets.QLabel("")
        self.validation_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        bottom_layout.addWidget(self.validation_label)

        if not self.providers_only:
            restart_text = "<p style='text-align: center;'>" + \
            _("Please restart Writing Tools for changes to take effect.") + \
            "</p>"

            restart_notice = QtWidgets.QLabel(restart_text)
            restart_notice.setStyleSheet(f"font-size: 15px; color: {'#cccccc' if colorMode == 'dark' else '#555555'}; font-style: italic;")
            restart_notice.setWordWrap(True)
            bottom_layout.addWidget(restart_notice)

        main_layout.addWidget(bottom_container)

        # Set appropriate window height based on screen size
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        max_height = int(screen.height() * 0.85)  # 85% of screen height
        desired_height = min(720, max_height)  # Cap at 720px or 85% of screen height
        self.resize(592, desired_height)  # Use an exact width of 592px so stuff looks good!

    def select_tab(self, tab_name):
        """Select a Settings tab when another UI entry point requests it."""
        if tab_name == "pinned_text" and self.settings_tabs is not None:
            index = self.settings_tabs.indexOf(self.pinned_text_page)
            if index >= 0:
                self.settings_tabs.setCurrentIndex(index)

    @staticmethod
    def toggle_autostart(state):
        """Toggle the autostart setting."""
        AutostartManager.set_autostart(state == 2)

    def show_button_visibility_dialog(self):
        PopupButtonVisibilityDialog(self.app, self).exec_()

    def export_settings(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            _("Export Writing Tools settings"),
            "writing-tools-settings.json",
            _("JSON files (*.json)")
        )
        if not path:
            return
        package = {
            "format": "writing-tools-settings",
            "format_version": 1,
            "config": self.app.config,
            "options": self.app.options,
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(package, handle, indent=2)
            QtWidgets.QMessageBox.information(
                self, _("Settings exported"), _("Your settings and prompt buttons were exported successfully.")
            )
        except (OSError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, _("Export failed"), str(exc))

    def import_settings(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            _("Import Writing Tools settings"),
            "",
            _("JSON files (*.json)")
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                package = json.load(handle)
            if (
                not isinstance(package, dict)
                or package.get("format") != "writing-tools-settings"
                or not isinstance(package.get("config"), dict)
                or not isinstance(package.get("options"), dict)
            ):
                raise ValueError(_("This file is not a valid Writing Tools settings export."))
            confirm = QtWidgets.QMessageBox.question(
                self,
                _("Replace current settings?"),
                _("Importing will replace the current settings and prompt buttons. Continue?"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self.app.save_config(package["config"])
            self.app.save_options(package["options"])
            self.app.load_config()
            self.app.load_options()
            self.app.register_hotkey()
            QtWidgets.QMessageBox.information(
                self,
                _("Settings imported"),
                _("Settings imported successfully. Close and reopen Writing Tools to refresh every window."),
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QtWidgets.QMessageBox.warning(self, _("Import failed"), str(exc))

    def mark_prompt_deleted(self, option_name):
        editors = self.option_prompt_inputs.get(option_name)
        if not editors:
            return
        editors["deleted"] = True
        editors["section"].hide()

    def _provider_selection_changed(self, index):
        if self._active_provider_index is not None:
            previous_provider = self.app.providers[self._active_provider_index]
            self._provider_drafts[previous_provider.provider_name] = (
                previous_provider.get_pending_config().copy()
            )

        self._active_provider_index = index
        provider = self.app.providers[index]
        self.init_provider_ui(provider, self.provider_container)
        if self.validation_label:
            self.validation_label.hide()

    def _build_updated_options(self):
        options = self.app.options.copy() if self.app.options else {}
        renamed = {}
        used_names = set()

        for original_name, option_config in options.items():
            editors = self.option_prompt_inputs.get(original_name)
            if not editors:
                if original_name in used_names:
                    QtWidgets.QMessageBox.warning(self, _("Duplicate name"), _("Every prompt must have a unique name."))
                    return None
                renamed[original_name] = option_config.copy()
                used_names.add(original_name)
                continue
            if editors["deleted"]:
                continue

            new_name = editors["name"].text().strip()
            if not new_name:
                QtWidgets.QMessageBox.warning(self, _("Missing name"), _("Prompt names cannot be blank."))
                return None
            if new_name in used_names:
                QtWidgets.QMessageBox.warning(
                    self,
                    _("Duplicate name"),
                    _("Every prompt must have a unique name. Please rename '%s'.") % new_name,
                )
                return None

            updated = option_config.copy()
            updated["visible"] = editors["visible"].isChecked()
            updated["prefix"] = editors["prefix"].text()
            updated["instruction"] = editors["instruction"].toPlainText()
            renamed[new_name] = updated
            used_names.add(new_name)

        return renamed

    def _current_provider_state(self):
        provider = self.app.providers[self.provider_dropdown.currentIndex()]
        return self.provider_dropdown.currentText(), provider.get_pending_config().copy()

    def test_provider_connection(self):
        provider = self.app.providers[self.provider_dropdown.currentIndex()]
        self._start_provider_validation(provider, provider.get_pending_config(), apply_after=False)

    def test_azure_speech(self):
        if self._validation_in_progress:
            return
        key = self.azure_speech_key_input.text().strip()
        region = self.azure_speech_region_input.text().strip()
        voice = self.azure_voice_dropdown.currentData()
        voice_name = self.azure_voice_dropdown.currentText()
        self._validation_in_progress = True
        self.azure_test_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.validation_label.setText(
            _("Creating a quick %s voice sample...") % voice_name
        )
        self.validation_label.setStyleSheet(
            f"color: {'#ffffff' if colorMode == 'dark' else '#333333'}; font-size: 14px;"
        )
        self.validation_label.show()

        def worker():
            try:
                self.app.azure_speech.test_connection(key, region, voice)
                success = True
                message = f"{voice_name} test completed successfully."
            except Exception as exc:
                success = False
                message = f"Azure Speech test failed: {exc}"
            self.azure_test_finished.emit(success, message)

        threading.Thread(target=worker, daemon=True).start()

    def check_azure_usage(self):
        if self._validation_in_progress:
            return
        self._validation_in_progress = True
        self.azure_usage_button.setEnabled(False)
        self.azure_usage_label.setText(_("Checking Azure Monitor usage..."))

        def worker():
            try:
                usage = get_speech_usage(self.app.config)
                if usage["quota"] is None:
                    message = _(
                        "%s: %s synthesized characters this month (%s tier). "
                        "A free F0 quota is not available for this tier; see Azure Cost Management for cost."
                    ) % (usage["resource_name"], f"{usage['characters']:,}", usage["sku"])
                else:
                    if usage.get("recent_daily_average", 0) > 0:
                        forecast = _(
                            " Recent 3-day average: %(average)s characters/day."
                            " At this pace, quota exhaustion is estimated around %(exhaustion)s."
                        ) % {
                            "average": f"{usage['recent_daily_average']:,.0f}",
                            "exhaustion": usage.get("estimated_exhaustion_date") or _("after the reset window"),
                        }
                    else:
                        forecast = _(
                            " Recent usage history is not sufficient for a forecast; check again over the next few days."
                        )
                    message = _(
                        "%s: %s / %s characters used (%0.1f%% used, %0.1f%% remaining). "
                        "Estimated reset: %s (%s days remaining). Checked %s.%s"
                    ) % (
                        usage["resource_name"], f"{usage['characters']:,}", f"{usage['quota']:,}",
                        usage["percent_used"], usage["percent_remaining"],
                        usage["reset_date"], usage["days_until_reset"], usage["checked_at"], forecast,
                    )
                self.app.save_config(self.app.config)
                self.azure_usage_finished.emit(True, message)
            except Exception as exc:
                self.azure_usage_finished.emit(False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot()
    def install_azure_cli(self):
        self._start_azure_component_install("cli", install_azure_cli_tool, _("Azure CLI"))

    @QtCore.Slot()
    def install_azure_powershell(self):
        self._start_azure_component_install(
            "powershell",
            install_azure_powershell_tool,
            _("Azure PowerShell"),
        )

    def _start_azure_component_install(self, component_name, installer, label):
        if self._azure_install_in_progress:
            return

        self._azure_install_in_progress = True
        if self.azure_cli_install_button is not None:
            self.azure_cli_install_button.setEnabled(False)
        if self.azure_powershell_install_button is not None:
            self.azure_powershell_install_button.setEnabled(False)
        self.azure_cli_status_label.setText(
            _("%s installation in progress...") % label
        )
        self.azure_cli_status_label.setStyleSheet(
            f"font-size: 13px; color: {'#ffcc66' if colorMode == 'dark' else '#8a6d3b'};"
        )

        def worker():
            try:
                installer()
                self.azure_install_finished.emit(component_name, True, _("%s install completed.") % label)
            except Exception as exc:
                self.azure_install_finished.emit(component_name, False, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(str, bool, str)
    def _finish_azure_install(self, component, success, message):
        self._azure_install_in_progress = False
        cli_available = bool(azure_cli_path())
        powershell_available = azure_powershell_available()
        cli_status = _("Azure CLI detected.") if cli_available else _("Azure CLI is not installed.")
        powershell_status = (
            _("Azure PowerShell detected.") if powershell_available
            else _("Azure PowerShell is not installed (optional).")
        )

        if self.azure_cli_install_button is not None:
            self.azure_cli_install_button.setEnabled(True)
            self.azure_cli_install_button.setVisible(not cli_available)
        if self.azure_powershell_install_button is not None:
            self.azure_powershell_install_button.setEnabled(True)
            self.azure_powershell_install_button.setVisible(not powershell_available)
        if not success:
            install_url = (
                AZURE_CLI_INSTALL_URL if component == "cli" else AZURE_POWERSHELL_INSTALL_URL
            )
            webbrowser.open(install_url)
            QtWidgets.QMessageBox.warning(
                self,
                _("Azure installation failed"),
                message + _("\n\nWe tried automated install and opened the official installer guide."),
            )

        color = '#63d471' if success else '#d93025'
        self.azure_cli_status_label.setText(f"{cli_status} {powershell_status}")
        self.azure_cli_status_label.setStyleSheet(
            f"font-size: 13px; color: {color};"
        )

        if success and not cli_available and component == "cli":
            self.azure_cli_status_label.setText(
                _("%s\n%s") % (_("%s install completed.") % _("Azure CLI"), f"{cli_status} {powershell_status}")
            )
        if success and not powershell_available and component == "powershell":
            self.azure_cli_status_label.setText(
                _("%s\n%s") % (_("%s install completed.") % _("Azure PowerShell"), f"{cli_status} {powershell_status}")
            )

        if not success:
            self.azure_cli_status_label.setStyleSheet(
                f"font-size: 13px; color: {'#d93025'};"
            )

    @QtCore.Slot(bool, str)
    def _finish_azure_usage_check(self, success, message):
        self._validation_in_progress = False
        self.azure_usage_button.setEnabled(True)
        self.azure_usage_label.setText(message)
        self.azure_usage_label.setStyleSheet(
            f"font-size: 13px; color: {'#63d471' if success else '#d93025'};"
        )

    @QtCore.Slot(bool, str)
    def _finish_azure_speech_test(self, success, message):
        self._validation_in_progress = False
        self.azure_test_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.validation_label.setText(message)
        self.validation_label.setStyleSheet(
            f"color: {'#63d471' if success else '#d93025'}; font-size: 14px; font-weight: bold;"
        )
        self.validation_label.show()

    def _start_provider_validation(self, provider, config, apply_after, options=None):
        if self._validation_in_progress:
            return
        self._validation_in_progress = True
        self._validation_apply_after = apply_after
        self._pending_options = options
        self._pending_provider = provider
        self._pending_provider_config = config
        self.save_button.setEnabled(False)
        self.validation_label.setText(_("Testing connection to the selected model..."))
        self.validation_label.setStyleSheet(
            f"color: {'#ffffff' if colorMode == 'dark' else '#333333'}; font-size: 14px;"
        )
        self.validation_label.show()

        def worker():
            try:
                success, message = provider.validate_connection(config)
            except Exception as exc:
                success, message = False, f"Connection test failed: {exc}"
            self.validation_finished.emit(success, message)

        threading.Thread(target=worker, daemon=True).start()

    @QtCore.Slot(bool, str)
    def _finish_provider_validation(self, success, message):
        self._validation_in_progress = False
        self.save_button.setEnabled(True)
        self.validation_label.setText(message)
        self.validation_label.setStyleSheet(
            f"color: {'#63d471' if success else '#d93025'}; font-size: 14px; font-weight: bold;"
        )
        self.validation_label.show()
        if success and self._validation_apply_after:
            self._apply_settings(self._pending_options)
        elif not success and self._validation_apply_after:
            QtWidgets.QMessageBox.warning(
                self,
                _("AI connection failed"),
                message + _("\n\nSettings were not saved. Check the credentials and selected model, then try again."),
            )

    def save_settings(self):
        """Validate changed AI settings, then save all settings."""
        options = None if self.providers_only else self._build_updated_options()
        if not self.providers_only and options is None:
            return

        provider = self.app.providers[self.provider_dropdown.currentIndex()]
        current_state = self._current_provider_state()
        must_validate = self.providers_only or current_state != self._initial_provider_state
        if must_validate:
            self._start_provider_validation(
                provider,
                provider.get_pending_config(),
                apply_after=True,
                options=options,
            )
            return
        self._apply_settings(options)

    def _apply_settings(self, options):
        if not self.providers_only:
            self.app.save_options(options)

        self.app.config['locale'] = 'en'

        if not self.providers_only:
            self.app.config['shortcut'] = self.shortcut_input.text()
            self.app.config['fast_track_action'] = self.fast_track_dropdown.currentData()
            self.app.config['theme'] = 'gradient' if self.gradient_radio.isChecked() else 'plain'
            self.app.config['review_before_insert'] = self.review_before_insert_checkbox.isChecked()
            if self.custom_prompt_checkbox is not None:
                self.app.config['show_custom_prompt_box'] = self.custom_prompt_checkbox.isChecked()
            self.app.config['read_aloud_provider'] = self.read_aloud_provider_dropdown.currentData()
            self.app.set_read_aloud_rate(self.read_aloud_speed_dropdown.currentData())
            self.app.config['azure_speech'] = {
                'key': self.azure_speech_key_input.text().strip(),
                'region': self.azure_speech_region_input.text().strip(),
                'voice': self.azure_voice_dropdown.currentData(),
                'natural_reading': self.natural_reading_checkbox.isChecked(),
            }
        else:
            self.app.create_tray_icon()

        self.app.config['streaming'] = False
        self.app.config['provider'] = self.provider_dropdown.currentText()

        # Mark config as updated for v8 (new users start with this flag set)
        self.app.config['is_config_file_updated_for_v8'] = True

        self.app.providers[self.provider_dropdown.currentIndex()].save_config()

        provider_name = self.app.config.get('provider', 'Gemini')
        self.app.current_provider = next(
            (provider for provider in self.app.providers if provider.provider_name == provider_name),
            self.app.providers[0]
        )

        self.app.current_provider.load_config(
            self.app.config.get("providers", {}).get(provider_name, {})
        )

        self.app.register_hotkey()
        self.providers_only = False
        self.close()

    def closeEvent(self, event):
        """Handle window close event."""
        if self.providers_only:
            self.close_signal.emit()
        super().closeEvent(event)

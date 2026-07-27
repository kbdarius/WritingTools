import os
import sys
import threading

from aiprovider import AIProvider, NoWheelComboBox
from azure_speech import AzureSpeechService
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QRadioButton, QScrollArea

from ui.AutostartManager import AutostartManager
from ui.CustomPopupWindow import PopupButtonVisibilityDialog
from ui.UIUtils import UIUtils, colorMode

_ = lambda x: x

class SettingsWindow(QtWidgets.QWidget):
    """
    The settings window for the application.
    Now with scrolling support for better usability on smaller screens.
    """
    close_signal = QtCore.Signal()
    validation_finished = QtCore.Signal(bool, str)
    azure_test_finished = QtCore.Signal(bool, str)

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
        self.review_before_insert_checkbox = None
        self.read_aloud_provider_dropdown = None
        self.azure_speech_key_input = None
        self.azure_speech_region_input = None
        self.azure_voice_dropdown = None
        self.azure_test_button = None
        self.option_prompt_inputs = {}
        self.save_button = None
        self.validation_label = None
        self._validation_in_progress = False
        self._pending_provider = None
        self._pending_provider_config = None
        self.init_ui()
        self.validation_finished.connect(self._finish_provider_validation)
        self.azure_test_finished.connect(self._finish_azure_speech_test)
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

        # Add provider settings
        for setting in provider.settings:
            setting.set_value(self.app.config["providers"][provider.provider_name].get(setting.name, setting.default_value))
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
            content.setStyleSheet("background: transparent;")
            layout = QtWidgets.QVBoxLayout(content)
            layout.setContentsMargins(30, 25, 30, 25)
            layout.setSpacing(16)
            scroll.setWidget(content)
            return scroll, layout

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        general_page, general_layout = create_scroll_page()
        prompts_page, prompts_layout = create_scroll_page()
        ai_page, ai_layout = create_scroll_page()
        if not self.providers_only:
            tabs.addTab(general_page, _("General"))
            tabs.addTab(prompts_page, _("Prompts"))
        tabs.addTab(ai_page, _("AI Provider"))
        main_layout.addWidget(tabs)

        content_layout = general_layout

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

        azure_settings = self.app.config.get('azure_speech', {})
        azure_key_label = QtWidgets.QLabel(_("Azure Speech resource key:"))
        azure_key_label.setStyleSheet(
            f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
        )
        content_layout.addWidget(azure_key_label)
        self.azure_speech_key_input = QtWidgets.QLineEdit(azure_settings.get('key', ''))
        self.azure_speech_key_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.azure_speech_key_input.setPlaceholderText(_("Paste the key from your Azure Speech resource"))
        content_layout.addWidget(self.azure_speech_key_input)

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

        # Add provider selection
        provider_label = QtWidgets.QLabel(_("Choose AI Provider:"))
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

        current_provider = self.app.config.get('provider', self.app.providers[0].provider_name)
        for provider in self.app.providers:
            self.provider_dropdown.addItem(provider.provider_name)
        self.provider_dropdown.setCurrentIndex(self.provider_dropdown.findText(current_provider))
        content_layout.addWidget(self.provider_dropdown)

        # Add horizontal separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        content_layout.addWidget(line)

        # Create container for provider UI
        self.provider_container = QtWidgets.QVBoxLayout()
        content_layout.addLayout(self.provider_container)

        # Initialize provider UI
        provider_instance = self.app.providers[self.provider_dropdown.currentIndex()]
        self.init_provider_ui(provider_instance, self.provider_container)
        self._initial_provider_state = (
            self.provider_dropdown.currentText(),
            provider_instance.get_pending_config().copy(),
        )

        # Connect provider dropdown
        self.provider_dropdown.currentIndexChanged.connect(
            self._provider_selection_changed
        )

        test_button = QtWidgets.QPushButton(_("Test Connection"))
        test_button.setToolTip(_("Verify that the selected credentials can reach the selected model."))
        test_button.clicked.connect(self.test_provider_connection)
        content_layout.addWidget(test_button)

        # Add horizontal separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        content_layout.addWidget(line)

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

    @staticmethod
    def toggle_autostart(state):
        """Toggle the autostart setting."""
        AutostartManager.set_autostart(state == 2)

    def show_button_visibility_dialog(self):
        PopupButtonVisibilityDialog(self.app, self).exec_()

    def mark_prompt_deleted(self, option_name):
        editors = self.option_prompt_inputs.get(option_name)
        if not editors:
            return
        editors["deleted"] = True
        editors["section"].hide()

    def _provider_selection_changed(self):
        provider = self.app.providers[self.provider_dropdown.currentIndex()]
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
            self.app.config['theme'] = 'gradient' if self.gradient_radio.isChecked() else 'plain'
            self.app.config['review_before_insert'] = self.review_before_insert_checkbox.isChecked()
            self.app.config['read_aloud_provider'] = self.read_aloud_provider_dropdown.currentData()
            self.app.config['azure_speech'] = {
                'key': self.azure_speech_key_input.text().strip(),
                'region': self.azure_speech_region_input.text().strip(),
                'voice': self.azure_voice_dropdown.currentData(),
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

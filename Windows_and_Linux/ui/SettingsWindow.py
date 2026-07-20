import os
import sys

from aiprovider import AIProvider
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
        self.option_prompt_inputs = {}
        self.init_ui()
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

        # Earlier scroll_area and scroll_content creation moved up
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Create scroll content widget
        scroll_content = QtWidgets.QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        
        # Style the scroll area for transparency
        scroll_area.setStyleSheet("""
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
        """)

        # Create a widget to hold the scrollable content
        scroll_content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(20)

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

            read_aloud_label = QtWidgets.QLabel(_("Read Aloud Voice:"))
            read_aloud_label.setStyleSheet(
                f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
            )
            content_layout.addWidget(read_aloud_label)

            self.read_aloud_provider_dropdown = QtWidgets.QComboBox()
            self.read_aloud_provider_dropdown.addItem(_("Writing Tools local voice"), "local")
            self.read_aloud_provider_dropdown.addItem(_("Microsoft Word Read Aloud"), "word")
            current_read_aloud_provider = self.app.config.get('read_aloud_provider', 'local')
            selected_index = self.read_aloud_provider_dropdown.findData(current_read_aloud_provider)
            self.read_aloud_provider_dropdown.setCurrentIndex(max(0, selected_index))
            self.read_aloud_provider_dropdown.setToolTip(
                _("Microsoft Word requires the installed Windows desktop version of Word. "
                  "Writing Tools uses a temporary document and closes it without saving.")
            )
            self.read_aloud_provider_dropdown.setStyleSheet(f"""
                font-size: 16px;
                padding: 5px;
                background-color: {'#444' if colorMode == 'dark' else 'white'};
                color: {'#ffffff' if colorMode == 'dark' else '#000000'};
                border: 1px solid {'#666' if colorMode == 'dark' else '#ccc'};
            """)
            content_layout.addWidget(self.read_aloud_provider_dropdown)

            # Add editable AI prompt section for every non-audio button.
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

                section_title = QtWidgets.QLabel(option_name)
                section_title.setStyleSheet(
                    f"font-size: 16px; font-weight: bold; color: {'#ffffff' if colorMode == 'dark' else '#333333'};"
                )
                section_layout.addWidget(section_title)

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
                    "prefix": prefix_input,
                    "instruction": instruction_input,
                }
                content_layout.addWidget(section)

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

        # Add provider selection
        provider_label = QtWidgets.QLabel(_("Choose AI Provider:"))
        provider_label.setStyleSheet(f"font-size: 16px; color: {'#ffffff' if colorMode == 'dark' else '#333333'};")
        content_layout.addWidget(provider_label)

        self.provider_dropdown = QtWidgets.QComboBox()
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

        # Connect provider dropdown
        self.provider_dropdown.currentIndexChanged.connect(
            lambda: self.init_provider_ui(self.app.providers[self.provider_dropdown.currentIndex()], self.provider_container)
        )

        # Add horizontal separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        content_layout.addWidget(line)

        # Set up scroll area with content
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # Create bottom container for save button and restart notice
        bottom_container = QtWidgets.QWidget()
        bottom_container.setStyleSheet("background: transparent;")  # Ensure transparency
        bottom_layout = QtWidgets.QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(30, 0, 30, 30)  # Match content margins except top
        bottom_layout.setSpacing(10)

        # Add save button to bottom container
        save_button = QtWidgets.QPushButton(_("Finish AI Setup") if self.providers_only else _("Save"))
        save_button.setStyleSheet("""
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
        save_button.clicked.connect(self.save_settings)
        bottom_layout.addWidget(save_button)

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

    def save_settings(self):
        """Save the current settings."""
        if not self.providers_only:
            options = self.app.options.copy() if self.app.options else {}
            for option_name, editors in self.option_prompt_inputs.items():
                if option_name not in options:
                    continue
                option_config = options[option_name]
                if option_config.get("action") == "read_aloud":
                    continue
                option_config["prefix"] = editors["prefix"].text()
                option_config["instruction"] = editors["instruction"].toPlainText()
            self.app.save_options(options)

        self.app.config['locale'] = 'en'

        if not self.providers_only:
            self.app.config['shortcut'] = self.shortcut_input.text()
            self.app.config['theme'] = 'gradient' if self.gradient_radio.isChecked() else 'plain'
            self.app.config['review_before_insert'] = self.review_before_insert_checkbox.isChecked()
            self.app.config['read_aloud_provider'] = self.read_aloud_provider_dropdown.currentData()
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

import sys, os, json, shutil, stat, getpass, hashlib
from PyQt6 import QtWidgets, QtGui, QtCore

# Mapping of keys to abbreviated labels.
KEY_MAPPING = {
    "Disable_FG_Override": "FG",
    "Disable_RR_Override": "RR",
    "Disable_SR_Override": "SR",
    "Disable_RR_Model_Override": "RR-M",
    "Disable_SR_Model_Override": "SR-M",
}

def compute_file_hash(path):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception as e:
        print(f"Error computing hash: {e}")
    return h.hexdigest()

def create_backup(main_path, backup_path, meta_path, log_func):
    """
    Create a backup of main_path and write meta data containing:
      - original_hash: hash of file before modification
      - modified_hash: hash of file after modification (initially same as original)
    """
    try:
        shutil.copy2(main_path, backup_path)
        original_hash = compute_file_hash(main_path)
        meta = {"original_hash": original_hash, "modified_hash": original_hash}
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        log_func(f"No backup found, creating new backup.\nBackup created at: {backup_path}")
        return meta
    except Exception as e:
        log_func(f"Error creating backup: {e}")
        return None

def load_backup_meta(meta_path):
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta
    except Exception:
        return None

def save_backup_meta(meta_path, meta):
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except Exception as e:
        print(f"Error saving backup meta: {e}")

def update_backup_if_obsolete(main_path, backup_path, meta_path, log_func):
    """
    Checks if the file at main_path has been externally updated compared to our stored
    meta ("modified_hash"). If so, create a new backup (i.e. treat the current file as new baseline).
    """
    if not os.path.exists(backup_path) or not os.path.exists(meta_path):
        return create_backup(main_path, backup_path, meta_path, log_func)
    meta = load_backup_meta(meta_path)
    if meta is None:
        log_func("Backup meta is invalid, creating new backup.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    current_hash = compute_file_hash(main_path)
    if current_hash != meta["modified_hash"]:
        log_func("External update detected. Updating backup to current file as new baseline.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    return meta

def recursive_process(obj, keys_to_update, updates):
    """
    Recursively traverse the JSON object (dict or list) and change any occurrence
    of a key (if its value is True) to False.
    
    'updates' is a dict mapping application names to a set of abbreviated labels.
    """
    modified = False
    if isinstance(obj, dict):
        for key in keys_to_update:
            if key in obj and obj[key] is True:
                obj[key] = False
                modified = True
                identifier = obj.get("LocalId") or obj.get("DisplayName") or "Unknown"
                updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        if "Application" in obj and isinstance(obj["Application"], dict):
            for key in keys_to_update:
                if key in obj["Application"] and obj["Application"][key] is True:
                    obj["Application"][key] = False
                    modified = True
                    identifier = obj["Application"].get("DisplayName") or obj.get("LocalId") or "Unknown"
                    updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        for value in obj.values():
            if isinstance(value, (dict, list)):
                if recursive_process(value, keys_to_update, updates):
                    modified = True
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                if recursive_process(item, keys_to_update, updates):
                    modified = True
    return modified

def modify_file(main_path, log_func):
    """
    Loads the JSON file at main_path, runs a recursive search to flip DLSS override keys
    (if True) to False. Prior to modification, a backup is updated (or created) along with metadata.
    """
    backup_path = main_path + ".backup"
    meta_path = main_path + ".backup.meta"
    meta = update_backup_if_obsolete(main_path, backup_path, meta_path, log_func)
    try:
        with open(main_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log_func(f"Error reading JSON: {e}")
        return False, None

    keys_to_update = list(KEY_MAPPING.keys())
    updates = {}  # Collect per-application update info.
    modified = recursive_process(data, keys_to_update, updates)
    if modified:
        try:
            with open(main_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            log_func("File has been updated.")
            mod_hash = compute_file_hash(main_path)
            meta["modified_hash"] = mod_hash
            save_backup_meta(meta_path, meta)
        except Exception as e:
            log_func(f"Error writing JSON: {e}")
            return False, None
    else:
        log_func("No modifications were made. Either keys were not found or already set to False.")
    
    # Log a concise summary for each application.
    for app, changes in updates.items():
        summary = ", ".join(f"{abbr} ✓" for abbr in sorted(changes))
        log_func(f"{app}: {summary}")
    
    if modified:
        log_func("Reboot recommended for changes to take effect.")
    return modified, meta

def revert_file(main_path, log_func):
    """
    Reverts main_path to the backup version if the file has not been externally updated
    since our last modification. Before copying, removes the read-only flag.
    """
    backup_path = main_path + ".backup"
    meta_path = main_path + ".backup.meta"
    if not os.path.exists(backup_path) or not os.path.exists(meta_path):
        log_func("No backup available to revert.")
        return False
    meta = load_backup_meta(meta_path)
    current_hash = compute_file_hash(main_path)
    if current_hash != meta["modified_hash"]:
        log_func("Cannot revert: file has been externally modified since our last update.")
        return False
    try:
        os.chmod(main_path, stat.S_IWRITE)
        shutil.copy2(backup_path, main_path)
        log_func("Reverted to backup.")
        meta["modified_hash"] = meta["original_hash"]
        save_backup_meta(meta_path, meta)
        return True
    except Exception as e:
        log_func(f"Error during revert: {e}")
        return False

class DLSSOverrideApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DLSS Override Editor")
        self.resize(800, 400)
        # Track whether a process was performed in this session.
        self.session_processed = False
        self.setup_ui()
        self.apply_dark_theme()

    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        # File path area.
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        username = getpass.getuser()
        default_path = fr"C:\Users\{username}\AppData\Local\NVIDIA Corporation\NVIDIA app\NvBackend\ApplicationStorage.json"
        self.path_edit.setText(default_path)
        path_layout.addWidget(self.path_edit)
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_file)
        path_layout.addWidget(self.browse_button)
        layout.addLayout(path_layout)

        # Checkbox for read-only option (checked by default).
        self.readonly_checkbox = QtWidgets.QCheckBox("Set file as read-only after modifications")
        self.readonly_checkbox.setChecked(True)
        layout.addWidget(self.readonly_checkbox)

        # Buttons: Process and Revert.
        btn_layout = QtWidgets.QHBoxLayout()
        self.process_button = QtWidgets.QPushButton("Process")
        self.process_button.clicked.connect(self.process_file)
        btn_layout.addWidget(self.process_button)
        self.revert_button = QtWidgets.QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert_file)
        btn_layout.addWidget(self.revert_button)
        layout.addLayout(btn_layout)

        # Log area.
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def apply_dark_theme(self):
        style = """
        /* Main window */
        QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
            font-family: "Segoe UI", sans-serif;
        }
        /* Line edits and text edits */
        QLineEdit, QTextEdit {
            background-color: #2d2d30;
            border: 1px solid #3e3e42;
            padding: 5px;
            border-radius: 3px;
            color: #e0e0e0;
        }
        /* Buttons */
        QPushButton {
            background-color: #007ACC;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            color: #ffffff;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #005A9E;
        }
        QPushButton:pressed {
            background-color: #003F73;
        }
        /* Checkboxes */
        QCheckBox {
            spacing: 5px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid #555555;
            background-color: #2d2d30;
        }
        QCheckBox::indicator:checked {
            border: 1px solid #007ACC;
            background-color: #007ACC;
        }
        """
        self.setStyleSheet(style)

    def log(self, message):
        self.log_text.append(message)

    def browse_file(self):
        current_path = self.path_edit.text().strip()
        initial_dir = os.path.dirname(current_path) if os.path.exists(current_path) else ""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select ApplicationStorage.json file", initial_dir, "JSON Files (*.json);;All Files (*)")
        if file_path:
            self.path_edit.setText(file_path)

    def process_file(self):
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm",
            f"Are you sure you want to modify this file?\n{file_path}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.log("Operation cancelled by user.")
            return
        modified, _ = modify_file(file_path, self.log)
        if modified:
            self.session_processed = True
        if modified and self.readonly_checkbox.isChecked():
            try:
                os.chmod(file_path, stat.S_IREAD)
                self.log("File set to read-only.")
            except Exception as e:
                self.log(f"Error setting file to read-only: {e}")

    def revert_file(self):
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Revert",
            f"Are you sure you want to revert changes to this file?\n{file_path}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.log("Revert cancelled by user.")
            return
        if revert_file(file_path, self.log):
            self.log("Revert successful.")
            # If a process was performed in this session, revert resets net changes.
            if self.session_processed:
                self.session_processed = False
            else:
                # If no process was performed in this session, treat revert as a modification.
                self.session_processed = True
        else:
            self.log("Revert failed or no valid backup available.")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.session_processed:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Reboot Recommended",
                "Changes have been made that require a reboot to take effect.\nWould you like to reboot now?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                os.system("shutdown /r /t 0")
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = DLSSOverrideApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

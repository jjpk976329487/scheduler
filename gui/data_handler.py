import json
import copy

from PyQt6.QtCore import QObject, pyqtSignal

class DataHandler(QObject):
    """
    Manages the application's state, including loading and saving session data.
    """
    data_loaded = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.data = self._get_default_data_structure()

    def _get_default_data_structure(self):
        """Returns a dictionary with the default empty state."""
        return {
            'params': {},
            'teachers_data': [],
            'subjects_data': [], # For Elementary
            'courses_data_raw_input': [], # For High School
            'cohort_constraints_list': [],
            'high_school_credits_db': {}
        }

    def get_data(self):
        """Returns a copy of the current data."""
        return copy.deepcopy(self.data)

    def set_data(self, new_data):
        """Sets the internal data and emits a signal."""
        self.data = new_data
        self.data_loaded.emit()

    def get_value(self, key, default=None):
        """Gets a specific value from the data dictionary."""
        return self.data.get(key, default)

    def set_value(self, key, value):
        """Sets a specific value in the data dictionary."""
        self.data[key] = value

    def save_session(self, filepath):
        """Saves the current session data to a JSON file."""
        if not filepath:
            return False, "File path cannot be empty."
        try:
            with open(filepath, 'w') as f:
                json.dump(self.data, f, indent=4)
            return True, f"Session saved successfully to {filepath}"
        except Exception as e:
            return False, f"Error saving session: {e}"

    def load_session(self, filepath):
        """Loads session data from a JSON file."""
        if not filepath:
            return False, "File path cannot be empty."
        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)
            
            if not isinstance(loaded_data, dict):
                return False, "Invalid file format: not a valid JSON object."

            self.data = self._get_default_data_structure()
            self.data.update(loaded_data)
            self.data_loaded.emit() # Notify listeners that data has changed
            return True, "Session loaded successfully."
        except FileNotFoundError:
            return False, "File not found."
        except json.JSONDecodeError:
            return False, "Invalid JSON format in file."
        except Exception as e:
            return False, f"Error loading session: {e}"
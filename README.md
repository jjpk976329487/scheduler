# School Schedule Automation

This project aims to automate the process of generating school schedules, providing a user-friendly graphical interface for inputting parameters and visualizing the results. The core of the application is built using Python and PyQt5 for the GUI, with a robust scheduling engine to handle complex constraints.

## Features

- **Intuitive GUI:** Built with PyQt5 for easy navigation and data input.
- **Wizard-based Interface:** Guides users through the scheduling process step-by-step.
- **Teacher Management:** Input and manage teacher availability and preferences.
- **Course Management:** Define courses, their requirements, and associated teachers.
- **School Parameter Configuration:** Set up school-specific parameters like bell times and room availability.
- **Automated Scheduling Engine:** Generates optimized schedules based on defined constraints.
- **Schedule Visualization:** View and export generated schedules.

## Project Structure

```
.
├── gui/
│   ├── __init__.py
│   ├── data_handler.py
│   ├── gui_app.py
│   ├── main.py
│   ├── schedule_editor.py
│   ├── scheduler_engine.py
│   └── wizard_pages/
│       ├── __init__.py
│       ├── page_courses.py
│       ├── page_results.py
│       ├── page_run.py
│       ├── page_schedule_structure.py
│       ├── page_school_params.py
│       └── page_teachers.py
├── tests/
│   └── test_schedule_editor.py
├── .gitignore
├── LICENSE.md
├── requirements.txt
└── README.md
```

- `gui/`: Contains all the source code for the graphical user interface.
    - `data_handler.py`: Manages data persistence and retrieval.
    - `gui_app.py`: Main application logic for the GUI.
    - `main.py`: Entry point for the GUI application.
    - `schedule_editor.py`: Provides functionalities for editing schedules.
    - `scheduler_engine.py`: The core scheduling algorithm and logic.
    - `wizard_pages/`: Contains individual pages for the wizard-based interface.
- `tests/`: Contains unit tests for the application.
- `.gitignore`: Specifies intentionally untracked files to ignore.
- `LICENSE.md`: The license under which this project is distributed.
- `requirements.txt`: Lists the Python dependencies required for the project.
- `README.md`: This file, providing an overview of the project.

## Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/jjpk976329487/scheduler.git
   cd scheduler
   ```

2. **Create a virtual environment (recommended):**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## Usage

To run the application, execute the `main.py` file:

```bash
python gui/main.py
```

This will launch the GUI, and you can then follow the wizard to input your school's data and generate schedules.

## Contributing

Contributions are welcome! Please feel free to fork the repository, make your changes, and submit a pull request. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the Creative Commons Attribution 4.0 International Public License - see the [LICENSE.md](LICENSE.md) file for details.

## Contact

For any questions or inquiries, please open an issue on the GitHub repository.
import sys
import os
import requests
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QPushButton, QLabel, QLineEdit, QMessageBox,
                            QFileDialog, QProgressBar, QFrame, QGridLayout,
                            QScrollArea)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon

API_BASE = "http://localhost:8000"

class ProcessingThread(QThread):
    progress_updated = pyqtSignal(int, str)
    processing_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.task_id = None

    def run(self):
        try:
            # Upload file
            with open(self.file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(f"{API_BASE}/upload", files=files)
                if not response.ok:
                    raise Exception(response.json().get('detail', 'Upload failed'))
                
                result = response.json()
                self.task_id = result['task_id']
                self.progress_updated.emit(5, "Processing started...")

            # Poll for status
            while True:
                status_response = requests.get(f"{API_BASE}/status/{self.task_id}")
                if not status_response.ok:
                    raise Exception("Failed to get status")
                
                status = status_response.json()
                self.progress_updated.emit(status['progress'], status['status'])
                
                if status['status'] == 'completed':
                    self.processing_complete.emit(status)
                    break
                
                time.sleep(1)

        except Exception as e:
            self.error_occurred.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Stem Separator")
        self.setMinimumSize(1000, 800)
        self.current_task_id = None
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        
        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f8f9fa;
            }
        """)
        
        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setSpacing(20)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Add title section
        title_frame = QFrame()
        title_frame.setStyleSheet("""
            QFrame {
                background-color: #0284c7;
                border-radius: 15px;
                padding: 30px;
            }
        """)
        title_layout = QVBoxLayout(title_frame)
        
        title = QLabel("Audio Stem Separator")
        title.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title)
        
        subtitle = QLabel("Upload your audio file and get separated stems: vocals, drums, bass, and more!")
        subtitle.setFont(QFont("Arial", 14))
        subtitle.setStyleSheet("color: #e0f2fe;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(subtitle)
        
        self.layout.addWidget(title_frame)
        
        # Add upload section
        upload_frame = QFrame()
        upload_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #ccc;
                border-radius: 15px;
                padding: 30px;
                background-color: white;
            }
            QFrame:hover {
                border-color: #0284c7;
                background-color: #f0f9ff;
            }
        """)
        upload_layout = QVBoxLayout(upload_frame)
        
        upload_title = QLabel("Choose Your Audio File")
        upload_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        upload_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.addWidget(upload_title)
        
        upload_subtitle = QLabel("Click to select")
        upload_subtitle.setStyleSheet("color: #666; font-size: 14px;")
        upload_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.addWidget(upload_subtitle)
        
        self.upload_btn = QPushButton("Select Audio File")
        self.upload_btn.setMinimumWidth(250)
        self.upload_btn.setMinimumHeight(50)
        self.upload_btn.setFont(QFont("Arial", 14))
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.upload_btn.clicked.connect(self.select_file)
        upload_layout.addWidget(self.upload_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        supported_formats = QLabel("Supported: MP3, WAV, FLAC, M4A, AAC, OGG")
        supported_formats.setStyleSheet("color: #666; font-size: 12px;")
        supported_formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        upload_layout.addWidget(supported_formats)
        
        self.layout.addWidget(upload_frame)
        
        # Add progress section (initially hidden)
        self.progress_frame = QFrame()
        self.progress_frame.setVisible(False)
        self.progress_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 30px;
            }
        """)
        progress_layout = QVBoxLayout(self.progress_frame)
        
        progress_title = QLabel("Processing Your Audio...")
        progress_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        progress_layout.addWidget(progress_title)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ccc;
                border-radius: 10px;
                text-align: center;
                height: 25px;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 8px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet("font-size: 14px; color: #666;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.status_label)
        
        self.layout.addWidget(self.progress_frame)
        
        # Add results section (initially hidden)
        self.results_frame = QFrame()
        self.results_frame.setVisible(False)
        self.results_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 30px;
            }
        """)
        results_layout = QVBoxLayout(self.results_frame)
        
        results_title = QLabel("Your Stems Are Ready!")
        results_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        results_layout.addWidget(results_title)
        
        self.download_all_btn = QPushButton("Download All Stems (ZIP)")
        self.download_all_btn.setMinimumHeight(50)
        self.download_all_btn.setFont(QFont("Arial", 14))
        self.download_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.download_all_btn.clicked.connect(self.download_all_stems)
        results_layout.addWidget(self.download_all_btn)
        
        self.stems_grid = QGridLayout()
        results_layout.addLayout(self.stems_grid)
        
        self.layout.addWidget(self.results_frame)
        
        # Add info section
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                padding: 30px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        
        how_it_works = QLabel("How It Works")
        how_it_works.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        info_layout.addWidget(how_it_works)
        
        description = QLabel("This tool uses advanced AI models to separate your audio into individual stems:")
        description.setStyleSheet("font-size: 14px;")
        info_layout.addWidget(description)
        
        stems_list = QLabel("• Vocals: Lead and background vocals\n"
                          "• Drums: Kick, snare, hi-hats, cymbals\n"
                          "• Bass: Bass guitar, sub-bass frequencies\n"
                          "• Other: Guitar, piano, synths, and other instruments")
        stems_list.setStyleSheet("color: #666; font-size: 14px;")
        info_layout.addWidget(stems_list)
        
        self.layout.addWidget(info_frame)
        
        # Center the window on screen
        self.center_window()
    
    def center_window(self):
        screen = QApplication.primaryScreen().geometry()
        window_size = self.geometry()
        x = (screen.width() - window_size.width()) // 2
        y = (screen.height() - window_size.height()) // 2
        self.move(x, y)
    
    def select_file(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.aac *.ogg)"
        )
        
        if file_name:
            self.process_file(file_name)
    
    def process_file(self, file_path):
        # Show progress section and hide results
        self.progress_frame.setVisible(True)
        self.results_frame.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting upload...")
        
        # Start processing thread
        self.processing_thread = ProcessingThread(file_path)
        self.processing_thread.progress_updated.connect(self.update_progress)
        self.processing_thread.processing_complete.connect(self.show_results)
        self.processing_thread.error_occurred.connect(self.show_error)
        self.processing_thread.start()
    
    def update_progress(self, value, status):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)
    
    def show_results(self, status):
        self.current_task_id = status.get('task_id')
        self.progress_frame.setVisible(False)
        self.results_frame.setVisible(True)
        
        # Clear existing stems
        while self.stems_grid.count():
            item = self.stems_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add stem download buttons
        stems = ['vocals', 'drums', 'bass', 'other']
        row = 0
        col = 0
        for stem in stems:
            btn = QPushButton(f"Download {stem.capitalize()}")
            btn.setMinimumHeight(40)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f8f9fa;
                    color: #0284c7;
                    border: 2px solid #0284c7;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #e0f2fe;
                }
            """)
            btn.clicked.connect(lambda checked, s=stem: self.download_stem(s))
            self.stems_grid.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
    
    def show_error(self, error_message):
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")
        self.progress_frame.setVisible(False)
    
    def download_stem(self, stem_name):
        if self.current_task_id:
            url = f"{API_BASE}/download/{self.current_task_id}/{stem_name}"
            os.startfile(url)
    
    def download_all_stems(self):
        if self.current_task_id:
            url = f"{API_BASE}/download/{self.current_task_id}"
            os.startfile(url)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Use Fusion style for a modern look
    
    # Set application-wide stylesheet
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f8f9fa;
        }
        QLabel {
            color: #212529;
        }
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

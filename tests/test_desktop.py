import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
import sys
import os
import tempfile
from desktop import MainWindow, ProcessingThread

@pytest.fixture
def app():
    return QApplication(sys.argv)

@pytest.fixture
def main_window(app):
    window = MainWindow()
    window.show()
    return window

@pytest.fixture
def test_audio_file():
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        f.write(b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00')
    yield f.name
    os.unlink(f.name)

def test_window_initialization(main_window):
    assert main_window.windowTitle() == "Audio Stem Separator"
    assert main_window.minimumSize().width() == 1000
    assert main_window.minimumSize().height() == 800

def test_upload_button_exists(main_window):
    assert hasattr(main_window, 'upload_btn')
    assert main_window.upload_btn.text() == "Select Audio File"

def test_progress_frame_initial_state(main_window):
    assert hasattr(main_window, 'progress_frame')
    assert not main_window.progress_frame.isVisible()

def test_results_frame_initial_state(main_window):
    assert hasattr(main_window, 'results_frame')
    assert not main_window.results_frame.isVisible()

def test_file_selection_dialog(main_window, test_audio_file, monkeypatch):
    def mock_get_open_file_name(*args, **kwargs):
        return test_audio_file, "WAV Files (*.wav)"
    
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_get_open_file_name)
    
    QTest.mouseClick(main_window.upload_btn, Qt.MouseButton.LeftButton)
    
    assert main_window.progress_frame.isVisible()

def test_processing_thread_initialization(test_audio_file):
    thread = ProcessingThread(test_audio_file)
    assert thread.file_path == test_audio_file
    assert thread.task_id is None

def test_error_handling(main_window, monkeypatch):
    def mock_get_open_file_name(*args, **kwargs):
        return "nonexistent.wav", "WAV Files (*.wav)"
    
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_get_open_file_name)
    
    QTest.mouseClick(main_window.upload_btn, Qt.MouseButton.LeftButton)
    
    assert main_window.status_label.text() != "Starting..."

def test_progress_bar_updates(main_window, test_audio_file, monkeypatch):
    def mock_get_open_file_name(*args, **kwargs):
        return test_audio_file, "WAV Files (*.wav)"
    
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_get_open_file_name)
    
    QTest.mouseClick(main_window.upload_btn, Qt.MouseButton.LeftButton)
    
    assert hasattr(main_window, 'progress_bar')
    assert main_window.progress_bar.isVisible()

def test_download_buttons(main_window, test_audio_file, monkeypatch):
    def mock_get_open_file_name(*args, **kwargs):
        return test_audio_file, "WAV Files (*.wav)"
    
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_get_open_file_name)
    
    QTest.mouseClick(main_window.upload_btn, Qt.MouseButton.LeftButton)
    
    assert hasattr(main_window, 'download_all_btn')
    assert main_window.download_all_btn.text() == "Download All Stems (ZIP)"

def test_window_center(main_window):
    main_window.center_window()
    assert hasattr(main_window, 'center_window')

def test_stems_grid_initialization(main_window):
    assert hasattr(main_window, 'stems_grid')
    assert main_window.stems_grid.count() == 0 
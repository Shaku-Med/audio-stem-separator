import os
import torch
import numpy as np
import librosa
import soundfile as sf
from scipy import signal

try:
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    DEMUCS_AVAILABLE = True
except ImportError:
    DEMUCS_AVAILABLE = False

class AudioSeparator:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.model_name = "htdemucs"
        
        if DEMUCS_AVAILABLE:
            self.load_model()
    
    def load_model(self):
        try:
            print(f"Loading model: {self.model_name}")
            self.model = get_model(self.model_name)
            self.model.to(self.device)
            print(f"Model loaded on {self.device}")
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
    
    async def separate_audio(self, audio_path: str, output_dir: str, task_id: str, tasks: dict):
        try:
            if not DEMUCS_AVAILABLE or self.model is None:
                return await self.simple_separation(audio_path, output_dir, task_id, tasks)
            
            tasks[task_id].progress = 20
            
            audio, sr = librosa.load(audio_path, sr=None, mono=False)
            
            if audio.ndim == 1:
                audio = np.stack([audio, audio])
            
            audio_tensor = torch.from_numpy(audio).float().to(self.device)
            if audio_tensor.dim() == 2:
                audio_tensor = audio_tensor.unsqueeze(0)
            
            tasks[task_id].progress = 50
            
            with torch.no_grad():
                separated = apply_model(self.model, audio_tensor, device=self.device)
            
            tasks[task_id].progress = 80
            
            stem_files = []
            stem_names = self.model.sources
            
            for i, stem_name in enumerate(stem_names):
                stem_audio = separated[0, i].cpu().numpy()
                stem_file = os.path.join(output_dir, f"{stem_name}.wav")
                sf.write(stem_file, stem_audio.T, sr)
                stem_files.append(stem_file)
            
            tasks[task_id].progress = 100
            tasks[task_id].status = "completed"
            tasks[task_id].stems = stem_files
            
            return stem_files
            
        except Exception as e:
            tasks[task_id].status = "failed"
            tasks[task_id].error = str(e)
            raise e
    
    async def simple_separation(self, audio_path: str, output_dir: str, task_id: str, tasks: dict):
        try:
            tasks[task_id].progress = 30
            
            audio, sr = librosa.load(audio_path, sr=None, mono=False)
            
            if audio.ndim == 1:
                audio = np.stack([audio, audio])
            
            tasks[task_id].progress = 60
            
            stems = {}
            
            vocals = (audio[0] + audio[1]) / 2
            stems['vocals'] = vocals
            
            instrumental = audio[0] - audio[1]
            stems['other'] = instrumental
            
            drums = self.extract_drums(audio, sr)
            stems['drums'] = drums
            
            bass = self.extract_bass(audio, sr)
            stems['bass'] = bass
            
            tasks[task_id].progress = 90
            
            stem_files = []
            for stem_name, stem_audio in stems.items():
                stem_file = os.path.join(output_dir, f"{stem_name}.wav")
                sf.write(stem_file, stem_audio, sr)
                stem_files.append(stem_file)
            
            tasks[task_id].progress = 100
            tasks[task_id].status = "completed"
            tasks[task_id].stems = stem_files
            
            return stem_files
            
        except Exception as e:
            tasks[task_id].status = "failed"
            tasks[task_id].error = str(e)
            raise e
    
    def extract_drums(self, audio, sr):
        hop_length = 512
        frame_length = 2048
        
        onset_frames = librosa.onset.onset_detect(
            y=audio.mean(axis=0), sr=sr, hop_length=hop_length
        )
        
        drum_mask = np.zeros(audio.shape[1])
        for frame in onset_frames:
            start = max(0, frame * hop_length - 1024)
            end = min(len(drum_mask), frame * hop_length + 1024)
            drum_mask[start:end] = 1
        
        return audio.mean(axis=0) * drum_mask
    
    def extract_bass(self, audio, sr):
        nyquist = sr / 2
        cutoff = 250 / nyquist
        b, a = signal.butter(4, cutoff, btype='low')
        
        mono_audio = audio.mean(axis=0)
        bass = signal.filtfilt(b, a, mono_audio)
        
        return bass 
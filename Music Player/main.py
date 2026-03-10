import os, glob, io, random, threading
import customtkinter as ctk
from tkinter import filedialog
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, USLT
from PIL import Image
import requests
import urllib.parse
try:
    import keyboard
except ImportError:
    pass
try:
    from pypresence import Presence
except ImportError:
    pass

# --- VLC Engine Configuration (Strict 64-bit for D: Drive) ---
VLC_PATH = r"D:\VLC"
if hasattr(os, 'add_dll_directory'):
    if os.path.exists(os.path.join(VLC_PATH, "libvlc.dll")):
        os.add_dll_directory(VLC_PATH)
    else:
        print("CRITICAL: VLC not found on D: drive. Check path.")
        exit()

# Now it is safe to import vlc
import vlc

class HingePlayer(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Music Player Premium")
        self.geometry("1100x750")  # Widescreen Desktop Layout
        self.configure(fg_color="#0a0a0a")
        
        # State
        self.current_theme = "dark"
        self.rpc = None
        try:
            self.rpc = Presence('1318041538318663711')
            self.rpc.connect()
        except Exception:
            self.rpc = None
            
        try:
            keyboard.on_press_key("play/pause media", lambda _: self.after(0, self.toggle))
            keyboard.on_press_key("next track", lambda _: self.after(0, self.next))
            keyboard.on_press_key("previous track", lambda _: self.after(0, self.prev))
        except Exception:
            pass
            
        self.player = vlc.Instance().media_player_new()
        self.playlist = []
        self.shuffled_playlist = []
        self.current_index = 0
        self.song_ended = False
        
        self.is_shuffle = False
        self.repeat_mode = 0    # 0: Off, 1: All, 2: One
        self.playback_speed = 1.0
        self.is_muted = False
        
        self.icon_size = (28, 28)
        self.load_assets()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ----------------------------------------------------
        # 1. LEFT SIDEBAR (Library & Art)
        # ----------------------------------------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=280, fg_color="#121212", corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.pack_propagate(False)
        
        ctk.CTkLabel(self.sidebar_frame, text="Library", font=("Segoe UI", 24, "bold"), text_color="#ffffff").pack(pady=(25, 15), padx=25, anchor="w")
        
        ctk.CTkButton(self.sidebar_frame, text="➕ Load Folder", command=self.load_dir, height=40, corner_radius=8,
                      font=("Segoe UI", 14, "bold"), fg_color="#8e44ad", hover_color="#7d3c98", text_color="#ffffff").pack(padx=25, fill="x")
        
        # Up Next
        self.lbl_up_next = ctk.CTkLabel(self.sidebar_frame, text="Up Next: —", font=("Segoe UI", 13, "italic"), text_color="#888888")
        self.lbl_up_next.pack(pady=(20, 5), padx=25, anchor="w")

        # Album Art
        self.album_container = ctk.CTkFrame(self.sidebar_frame, width=240, height=240, fg_color="#181818", corner_radius=12)
        self.album_container.pack(pady=(20, 0), padx=20, side="bottom", before=None)
        self.album_container.pack_propagate(False)
        self.album_label = ctk.CTkLabel(self.album_container, text="🎵", font=("Segoe UI", 80), text_color="#333333")
        self.album_label.pack(expand=True, fill="both")

        # ----------------------------------------------------
        # 2. MAIN CONTENT AREA (Search, Playlist, Lyrics)
        # ----------------------------------------------------
        self.main_frame = ctk.CTkFrame(self, fg_color="#0a0a0a", corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Top Util Bar
        top_util = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        top_util.pack(fill="x", pady=(0, 15))
        
        self.btn_theme = ctk.CTkButton(top_util, text="☀️", width=40, height=40, font=("Segoe UI", 18), fg_color="#181818", hover_color="#2a2a2a", corner_radius=20, command=self.toggle_theme)
        self.btn_theme.pack(side="right")
        self.btn_sleep = ctk.CTkButton(top_util, text="⏲️", width=40, height=40, font=("Segoe UI", 18), fg_color="#181818", hover_color="#2a2a2a", corner_radius=20, command=self.set_sleep_timer)
        self.btn_sleep.pack(side="right", padx=10)
        
        ctk.CTkLabel(top_util, text="Explore", font=("Segoe UI", 32, "bold")).pack(side="left")

        # Tabs for Playlist / Lyrics
        self.tabs = ctk.CTkTabview(self.main_frame, fg_color="#121212", corner_radius=15)
        self.tabs.pack(fill="both", expand=True)
        self.tab_playlist = self.tabs.add("Playlist")
        self.tab_lyrics = self.tabs.add("Lyrics")
        
        # ---- Playlist Tab ----
        self.search_var = ctk.StringVar()
        # FIX: using trace_add instead of trace to remove the deprecation warning
        self.search_var.trace_add("write", self.update_playlist_ui)
        
        srch_frame = ctk.CTkFrame(self.tab_playlist, fg_color="transparent")
        srch_frame.pack(fill="x", pady=(5, 10), padx=10)
        ctk.CTkLabel(srch_frame, text="🔍", font=("Segoe UI", 18)).pack(side="left", padx=(0, 10))
        self.search_entry = ctk.CTkEntry(srch_frame, textvariable=self.search_var, placeholder_text="Search songs...", height=35, corner_radius=8, font=("Segoe UI", 14), fg_color="#181818", border_width=0)
        self.search_entry.pack(side="left", fill="x", expand=True)
        
        self.playlist_frame = ctk.CTkScrollableFrame(self.tab_playlist, fg_color="transparent")
        self.playlist_frame.pack(fill="both", expand=True)
        
        # ---- Lyrics Tab ----
        self.lyrics_textbox = ctk.CTkTextbox(self.tab_lyrics, wrap="word", fg_color="transparent", font=("Segoe UI", 16))
        self.lyrics_textbox.pack(fill="both", expand=True, padx=20, pady=20)
        self.lyrics_textbox.insert("0.0", "Lyrics will appear here.")
        self.lyrics_textbox.configure(state="disabled")

        # ----------------------------------------------------
        # 3. BOTTOM CONTROL BAR (Spotify Style)
        # ----------------------------------------------------
        self.bottom_bar = ctk.CTkFrame(self, height=90, fg_color="#181818", corner_radius=0)
        self.bottom_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.bottom_bar.grid_propagate(False)
        self.bottom_bar.pack_propagate(False)
        
        # Left: Now Playing Info
        self.np_frame = ctk.CTkFrame(self.bottom_bar, width=280, fg_color="transparent")
        self.np_frame.pack(side="left", fill="y", padx=20)
        self.np_frame.pack_propagate(False)
        
        self.lbl_song = ctk.CTkLabel(self.np_frame, text="Ready to meet your vibe?", font=("Segoe UI", 16, "bold"), text_color="#ffffff", anchor="w")
        self.lbl_song.pack(pady=(20, 0), fill="x")
        self.lbl_artist = ctk.CTkLabel(self.np_frame, text="Load a folder to find your perfect track.", font=("Segoe UI", 12), text_color="#aaaaaa", anchor="w")
        self.lbl_artist.pack(fill="x")
        
        # Center: Playback Controls & Progress
        self.center_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        self.center_frame.pack(side="left", expand=True, fill="both")
        
        ctrl_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent")
        ctrl_frame.pack(pady=(12, 0))
        
        self.btn_shuffle = ctk.CTkButton(ctrl_frame, text="🔀", font=("Segoe UI", 18), width=35, height=35, fg_color="transparent", text_color="#555555", hover_color="#2a2a2a", command=self.toggle_shuffle)
        self.btn_shuffle.pack(side="left", padx=10)
        
        ctk.CTkButton(ctrl_frame, text="", image=self.img_prev, command=self.prev, width=35, height=35, fg_color="transparent", hover_color="#2a2a2a", corner_radius=20).pack(side="left", padx=5)
        self.play_btn = ctk.CTkButton(ctrl_frame, text="", image=self.img_play, command=self.toggle, width=45, height=45, corner_radius=25, fg_color="#8e44ad", hover_color="#7d3c98")
        self.play_btn.pack(side="left", padx=15)
        ctk.CTkButton(ctrl_frame, text="", image=self.img_next, command=self.next, width=35, height=35, fg_color="transparent", hover_color="#2a2a2a", corner_radius=20).pack(side="left", padx=5)
        
        self.btn_repeat = ctk.CTkButton(ctrl_frame, text="🔁", font=("Segoe UI", 18), width=35, height=35, fg_color="transparent", text_color="#555555", hover_color="#2a2a2a", command=self.toggle_repeat)
        self.btn_repeat.pack(side="left", padx=10)
        
        prog_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent")
        prog_frame.pack(fill="x", padx=40, pady=(2, 0))
        self.lbl_time = ctk.CTkLabel(prog_frame, text="0:00", font=("Segoe UI", 11), text_color="#888888")
        self.lbl_time.pack(side="left")
        self.slider = ctk.CTkSlider(prog_frame, from_=0, to=100, command=self.seek_position, height=12, button_color="#8e44ad", progress_color="#8e44ad", button_hover_color="#ffffff")
        self.slider.pack(side="left", fill="x", expand=True, padx=10)
        self.lbl_total = ctk.CTkLabel(prog_frame, text="0:00", font=("Segoe UI", 11), text_color="#888888")
        self.lbl_total.pack(side="right")
        
        # Right: Volume & Extras
        self.right_frame = ctk.CTkFrame(self.bottom_bar, width=280, fg_color="transparent")
        self.right_frame.pack(side="right", fill="y", padx=20)
        self.right_frame.pack_propagate(False)
        
        vol_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        vol_frame.pack(side="right", pady=30)
        
        self.btn_speed = ctk.CTkButton(vol_frame, text="1.0x", font=("Segoe UI", 11, "bold"), text_color="#888888", width=40, height=22, fg_color="#222222", hover_color="#333333", corner_radius=10, command=self.cycle_speed)
        self.btn_speed.pack(side="left", padx=(0, 15))
        
        self.btn_mute = ctk.CTkButton(vol_frame, text="🔊", font=("Segoe UI", 16), text_color="#888888", width=30, height=30, fg_color="transparent", hover_color="#2a2a2a", command=self.toggle_mute)
        self.btn_mute.pack(side="left", padx=(0, 5))
        self.vol_slider = ctk.CTkSlider(vol_frame, from_=0, to=100, width=100, height=10, command=self.set_volume, button_color="#555555", progress_color="#888888", button_hover_color="#ffffff")
        self.vol_slider.pack(side="left")
        self.vol_slider.set(100)

        self.update_loop()

    def load_assets(self):
        assets_dir = os.path.join(os.path.dirname(__file__), "assets")
        try:
            self.img_play = ctk.CTkImage(Image.open(os.path.join(assets_dir, "play.png")), size=(20, 20))
            self.img_pause = ctk.CTkImage(Image.open(os.path.join(assets_dir, "pause.png")), size=(20, 20))
            self.img_next = ctk.CTkImage(Image.open(os.path.join(assets_dir, "next.png")), size=(18, 18))
            self.img_prev = ctk.CTkImage(Image.open(os.path.join(assets_dir, "prev.png")), size=(18, 18))
        except Exception:
            self.img_play = self.img_pause = self.img_next = self.img_prev = None

    def format_time(self, ms):
        if ms < 0: return "0:00"
        s = ms // 1000
        m = s // 60
        s = s % 60
        return f"{m}:{s:02d}"

    def load_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.playlist = sorted(glob.glob(os.path.join(path, "*.mp3")))
            if self.playlist:
                self.shuffled_playlist = list(self.playlist)
                if self.is_shuffle: random.shuffle(self.shuffled_playlist)
                self.current_index = 0
                self.update_playlist_ui()
                self.play_current()

    def update_playlist_ui(self, *args):
        for widget in self.playlist_frame.winfo_children():
            widget.destroy()
        
        query = self.search_var.get().lower()
        active_list = self.get_active_playlist()
        for idx, song_path in enumerate(active_list):
            meta = self.read_metadata(song_path, shallow=True)
            search_str = f"{meta['title']} {meta['artist']}".lower()
            
            if query in search_str:
                row = ctk.CTkFrame(self.playlist_frame, fg_color="transparent", corner_radius=8)
                row.pack(fill="x", pady=2, padx=5)
                
                # Check if playing
                is_playing_this = (idx == self.current_index)
                t_color = "#8e44ad" if is_playing_this else ("#ffffff" if self.current_theme == "dark" else "#111111")
                bg_color = "#222222" if is_playing_this else "transparent"
                h_color = "#333333" if self.current_theme == "dark" else "#dddddd"
                
                btn = ctk.CTkButton(row, text=f"{meta['title']}  •  {meta['artist']}", anchor="w", fg_color=bg_color,
                                    font=("Segoe UI", 14, "bold" if is_playing_this else "normal"),
                                    text_color=t_color, hover_color=h_color, height=45,
                                    command=lambda i=idx: self.play_from_playlist(i))
                btn.pack(fill="both", expand=True)

    def play_from_playlist(self, idx):
        self.current_index = idx
        self.play_current()

    def get_active_playlist(self):
        return self.shuffled_playlist if self.is_shuffle else self.playlist

    def read_metadata(self, path, shallow=False):
        meta = {"title": os.path.splitext(os.path.basename(path))[0][:45], "artist": "Unknown Artist", "lyrics": ""}
        try:
            audio = ID3(path)
            if 'TIT2' in audio: meta['title'] = str(audio['TIT2'])
            if 'TPE1' in audio: meta['artist'] = str(audio['TPE1'])
            if not shallow:
                for key in audio.keys():
                    if key.startswith("USLT"):
                        meta['lyrics'] = str(audio[key])
                        break
        except Exception:
            pass
        return meta

    def update_up_next(self):
        active_list = self.get_active_playlist()
        if len(active_list) > 1:
            next_idx = self.current_index + 1
            if next_idx >= len(active_list):
                next_idx = 0 if self.repeat_mode == 1 else -1
            if next_idx != -1:
                next_meta = self.read_metadata(active_list[next_idx], shallow=True)
                self.lbl_up_next.configure(text=f"Up Next: {next_meta['title'][:35]}")
            else:
                self.lbl_up_next.configure(text="Up Next: —")
        else:
            self.lbl_up_next.configure(text="Up Next: —")

    def play_current(self):
        active_list = self.get_active_playlist()
        if not active_list or self.current_index >= len(active_list): return
        song = active_list[self.current_index]
        
        meta = self.read_metadata(song)
        self.lbl_song.configure(text=meta['title'])
        self.lbl_artist.configure(text=meta['artist'])
        
        self.lyrics_textbox.configure(state="normal")
        self.lyrics_textbox.delete("0.0", "end")
        self.lyrics_textbox.insert("0.0", meta['lyrics'] if meta['lyrics'] else "\n\n(No lyrics found in file.)\n\nEnjoy the instrumental!")
        self.lyrics_textbox.configure(state="disabled")
        
        self.update_playlist_ui()
        
        self.player.set_media(vlc.Instance().media_new(song))
        self.player.play()
        self.player.set_rate(self.playback_speed)
        
        if self.img_pause: self.play_btn.configure(image=self.img_pause)
        self.song_ended = False
        self.extract_art(song)
        self.update_up_next()
        
        if self.rpc:
            try:
                self.rpc.update(state=meta['artist'][:128], details=meta['title'][:128], large_image="logo", large_text="Music Player")
            except Exception:
                pass

    def extract_art(self, path):
        try:
            audio = ID3(path)
            for key in audio.keys():
                if key.startswith('APIC'):
                    tag = audio[key]
                    img = Image.open(io.BytesIO(tag.data))
                    ctk_img = ctk.CTkImage(img, size=(240, 240))
                    self.album_label.configure(image=ctk_img, text="")
                    return
        except Exception:
            pass
            
        self.album_label.configure(image=None, text="Loading...")
        threading.Thread(target=self.fetch_itunes_art, args=(path,), daemon=True).start()
        
    def fetch_itunes_art(self, path):
        try:
            meta = self.read_metadata(path, shallow=True)
            title = meta.get('title', '')
            artist = meta.get('artist', '')
            if title and artist != "Unknown Artist":
                query = urllib.parse.quote(f"{title} {artist}")
                url = f"https://itunes.apple.com/search?term={query}&limit=1&entity=song"
                resp = requests.get(url, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    if data['resultCount'] > 0:
                        art_url = data['results'][0]['artworkUrl100'].replace('100x100bb', '600x600bb')
                        img_data = requests.get(art_url, timeout=3).content
                        img = Image.open(io.BytesIO(img_data))
                        ctk_img = ctk.CTkImage(img, size=(240, 240))
                        self.after(0, lambda: self.album_label.configure(image=ctk_img, text=""))
                        return
        except Exception:
            pass
        self.after(0, lambda: self.album_label.configure(image=None, text="🎵"))

    def toggle(self):
        if not self.playlist: return
        if self.player.is_playing(): 
            self.player.pause()
            if self.img_play: self.play_btn.configure(image=self.img_play)
        else: 
            self.player.play()
            if self.img_pause: self.play_btn.configure(image=self.img_pause)

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        self.btn_shuffle.configure(text_color="#ffffff" if self.is_shuffle else "#555555")
        if not self.playlist: return
        
        current_song = self.get_active_playlist()[self.current_index]
        if self.is_shuffle:
            self.shuffled_playlist = list(self.playlist)
            random.shuffle(self.shuffled_playlist)
            self.current_index = self.shuffled_playlist.index(current_song)
        else:
            self.current_index = self.playlist.index(current_song)
        self.update_up_next()
        self.update_playlist_ui()

    def toggle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        if self.repeat_mode == 0:
            self.btn_repeat.configure(text_color="#555555", text="🔁")
        elif self.repeat_mode == 1:
            self.btn_repeat.configure(text_color="#ffffff", text="🔁")
        else:
            self.btn_repeat.configure(text_color="#ffffff", text="🔂")
        self.update_up_next()
        
    def cycle_speed(self):
        speeds = [0.5, 1.0, 1.25, 1.5, 2.0]
        idx = speeds.index(self.playback_speed)
        self.playback_speed = speeds[(idx + 1) % len(speeds)]
        self.btn_speed.configure(text=f"{self.playback_speed}x")
        self.player.set_rate(self.playback_speed)

    def toggle_mute(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.player.audio_set_volume(0)
            self.btn_mute.configure(text="🔇", text_color="#e74c3c")
        else:
            self.player.audio_set_volume(int(self.vol_slider.get()))
            self.btn_mute.configure(text="🔊", text_color="#888888")

    def next(self): 
        active_list = self.get_active_playlist()
        if not active_list: return
        
        if self.repeat_mode == 2: # Repeat One
            self.player.set_position(0)
            self.player.play()
            return
            
        self.current_index += 1
        if self.current_index >= len(active_list):
            if self.repeat_mode == 1: # Repeat All
                if self.is_shuffle: random.shuffle(self.shuffled_playlist)
                self.current_index = 0
            else:
                self.current_index -= 1
                self.player.stop()
                if self.img_play: self.play_btn.configure(image=self.img_play)
                return
        self.play_current()
        
    def prev(self): 
        active_list = self.get_active_playlist()
        if not active_list: return
            
        self.current_index -= 1
        if self.current_index < 0:
            if self.repeat_mode == 1:
                self.current_index = len(active_list) - 1
            else:
                self.current_index = 0
        self.play_current()
    
    def seek_position(self, v):
        self.player.set_position(float(v)/100)
        
    def set_volume(self, v):
        if self.is_muted:
            self.toggle_mute()
        self.player.audio_set_volume(int(v))

    def set_sleep_timer(self):
        timers = [0, 15, 30, 45, 60]
        if not hasattr(self, 'sleep_minutes_left'):
            self.sleep_minutes_left = 0
            self.sleep_timer_id = None
            
        try:
            nxt_idx = timers.index(self.sleep_minutes_left) + 1
            if nxt_idx >= len(timers): nxt_idx = 0
        except ValueError:
            nxt_idx = 1
            
        self.sleep_minutes_left = timers[nxt_idx]
            
        if self.sleep_minutes_left > 0:
            self.btn_sleep.configure(text_color="#8e44ad", text=f"{self.sleep_minutes_left}m")
            if self.sleep_timer_id:
                self.after_cancel(self.sleep_timer_id)
            self.sleep_timer_id = self.after(60000, self.sleep_timer_tick)
        else:
            self.btn_sleep.configure(text_color="#ffffff", text="⏲️")
            if self.sleep_timer_id:
                self.after_cancel(self.sleep_timer_id)
                self.sleep_timer_id = None

    def sleep_timer_tick(self):
        self.sleep_minutes_left -= 1
        if self.sleep_minutes_left <= 0:
            self.btn_sleep.configure(text_color="#ffffff", text="⏲️")
            self.sleep_timer_id = None
            if self.player.is_playing():
                self.toggle()
        else:
            self.btn_sleep.configure(text=f"{self.sleep_minutes_left}m")
            self.sleep_timer_id = self.after(60000, self.sleep_timer_tick)

    def toggle_theme(self):
        if self.current_theme == "dark":
            self.current_theme = "light"
            ctk.set_appearance_mode("light")
            self.configure(fg_color="#f5f5f5")
            self.main_frame.configure(fg_color="#f5f5f5")
            self.sidebar_frame.configure(fg_color="#e0e0e0")
            self.bottom_bar.configure(fg_color="#ffffff")
            self.tabs.configure(fg_color="#e8e8e8")
            self.lbl_song.configure(text_color="#111111")
            self.btn_theme.configure(text="🌙")
            self.update_playlist_ui()
        else:
            self.current_theme = "dark"
            ctk.set_appearance_mode("dark")
            self.configure(fg_color="#0a0a0a")
            self.main_frame.configure(fg_color="#0a0a0a")
            self.sidebar_frame.configure(fg_color="#121212")
            self.bottom_bar.configure(fg_color="#181818")
            self.tabs.configure(fg_color="#121212")
            self.lbl_song.configure(text_color="#ffffff")
            self.btn_theme.configure(text="☀️")
            self.update_playlist_ui()

    def update_loop(self):
        length = self.player.get_length()
        if length > 0:
            pos = self.player.get_position()
            self.slider.set(pos * 100)
            
            time_now = self.player.get_time()
            self.lbl_time.configure(text=self.format_time(time_now))
            self.lbl_total.configure(text=self.format_time(length))
            
            if self.player.get_state() == 6 and not self.song_ended and self.playlist:
                self.song_ended = True
                self.next()
        self.after(1000, self.update_loop)

if __name__ == "__main__":
    HingePlayer().mainloop()
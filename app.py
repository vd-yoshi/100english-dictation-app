# ==========================================
# 英語ディクテーション Webアプリ (Streamlit完全版)
# ==========================================
import base64
from collections import Counter
from datetime import datetime
import difflib
import os
import re
import urllib.request
import zipfile
import pandas as pd
import streamlit as st
from streamlit_mic_recorder import speech_to_text

# --------------------------------------------------
# 1. ページ基本設定
# --------------------------------------------------
st.set_page_config(
    page_title="英語ディクテーション Web", layout="wide", page_icon="🎧"
)

# --------------------------------------------------
# 2. パスワード保護機能
# --------------------------------------------------


def check_password():
  """パスワード認証（未認証時は画面をロック）"""
  if st.session_state.get("password_correct", False):
    return True

  st.title("🔒 ログイン")
  st.write("このアプリを利用するにはパスワードが必要です。")

  password_input = st.text_input("パスワードを入力してください：", type="password")

  if st.button("ログイン", type="primary"):
    # Streamlit CloudのSecrets設定があればそれを優先、なければ "100speak" を使用
    target_password = st.secrets.get("PASSWORD", "100speak")

    if password_input == target_password:
      st.session_state["password_correct"] = True
      st.rerun()
    else:
      st.error("⚠️ パスワードが正しくありません。")

  return False


# パスワード認証が完了するまで以降のコードを実行しない
if not check_password():
  st.stop()

# --------------------------------------------------
# 3. 定数・パス設定 & 音声自動ダウンロード
# --------------------------------------------------
AUDIO_EXTRACT_DIR = "audio_files"
TXT_PATH = "whisper.txt"
CSV_PATH = "dictation_history.csv"


@st.cache_resource
def setup_audio_files():
  """GitHub Releasesから音声ZIPを自動ダウンロード＆解凍"""
  audio_dir = AUDIO_EXTRACT_DIR
  if not os.path.exists(audio_dir) or len(os.listdir(audio_dir)) == 0:
    os.makedirs(audio_dir, exist_ok=True)
    zip_path = "temp_audio.zip"
    # GitHub Releasesのwhisper.zipのURL
    download_url = "https://github.com/vd-Yoshi/100english-dictation-app/releases/download/v1.0.0/whisper.zip"

    with st.spinner(
        "初回起動中：音声ファイルをダウンロードしています（数秒〜数分かかります）..."
    ):
      try:
        urllib.request.urlretrieve(download_url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
          zip_ref.extractall(audio_dir)
        if os.path.exists(zip_path):
          os.remove(zip_path)
      except Exception as e:
        st.error(f"音声ファイルのダウンロードに失敗しました: {e}")


# アプリ起動時に音声ファイルを準備
setup_audio_files()

ARTICLES = {"a", "an", "the"}
PREPOSITIONS = {
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "about",
    "into",
    "through",
    "over",
    "under",
}
PRONOUNS = {
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "my",
    "your",
    "his",
    "its",
    "our",
    "their",
    "this",
    "that",
}

# --------------------------------------------------
# 4. 補助関数
# --------------------------------------------------


@st.cache_data
def load_transcripts():
  """テキストファイルの読み込み"""
  transcripts = {}
  if os.path.exists(TXT_PATH):
    with open(TXT_PATH, "r", encoding="utf-8") as f:
      lines = [line.strip() for line in f.readlines() if line.strip()]
    for idx, line in enumerate(lines, 1):
      match = re.match(r"^Day\s*(\d+)[:\s-]*(.*)", line, re.IGNORECASE)
      if match:
        transcripts[int(match.group(1))] = match.group(2).strip()
      else:
        transcripts[idx] = line
  return transcripts


def get_audio_path(day):
  """音声ファイルの自動判定"""
  if not os.path.exists(AUDIO_EXTRACT_DIR):
    return None
  valid_exts = (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg")
  for root, dirs, files in os.walk(AUDIO_EXTRACT_DIR):
    for file in files:
      if file.startswith("."):
        continue
      if file.lower().endswith(valid_exts):
        numbers = re.findall(r"\d+", file)
        if day in [int(n) for n in numbers]:
          return os.path.join(root, file)
  return None


def parse_transcript_entry(raw_text):
  """英文と日本語訳の自動分離"""
  if not raw_text:
    return "", ""
  for sep in ["|", "/", "／", "\t"]:
    if sep in raw_text:
      parts = raw_text.split(sep, 1)
      return parts[0].strip(), parts[1].strip()
  return raw_text.strip(), "（日本語訳データなし）"


def clean_text(text):
  return re.sub(r"[^\w\s]", "", text.lower()).split()


# --------------------------------------------------
# 5. アプリメイン画面
# --------------------------------------------------
st.title("🎧 英語ディクテーション トレーニング")

transcripts = load_transcripts()

# サイドバー設定
st.sidebar.header("⚙️ 設定")
day = st.sidebar.selectbox(
    "学習日を選択", [i for i in range(1, 101)], format_func=lambda x: f"Day {x}"
)

if st.sidebar.button("🔒 ログアウト"):
  st.session_state["password_correct"] = False
  st.rerun()

# メインタブ
tab1, tab2 = st.tabs(["🎧 ディクテーション学習", "📊 弱点分析レポート"])

# --- TAB 1: ディクテーション学習 ---
with tab1:
  col_left, col_right = st.columns([1, 1])

  with col_left:
    st.subheader(f"Day {day} の学習")
    audio_file = get_audio_path(day)

    # ステップ1：音声を聞く
    st.markdown("#### **Step 1: 音声を聴く**")
    st.caption(
        "🎧 音声を再生してしっかりリスニングします。（聴き終わったら/途中で止める場合はプレイヤーの一時停止ボタンを押してください）"
    )

    if audio_file and os.path.exists(audio_file):
      st.audio(audio_file)
    else:
      st.warning(f"⚠️ Day {day} の音声ファイルが見つかりません。")

    st.markdown("---")

    # ステップ2：マイクで話す
    st.markdown("#### **Step 2: マイクに向かって話す**")
    st.caption(
        "🎙️ 下のボタンを押して発話してください。（複数回に分けて話すと文章が後ろに追加されます）"
    )

    # セッションステートの初期化
    if f"input_text_{day}" not in st.session_state:
      st.session_state[f"input_text_{day}"] = ""
    if f"last_spoken_{day}" not in st.session_state:
      st.session_state[f"last_spoken_{day}"] = ""

    # 🎙️ マイクからの音声認識
    spoken_text = speech_to_text(
        language="en",  # 英語で認識
        start_prompt="🎙️ 録音を開始する（話す）",
        stop_prompt="⏹️ 録音を停止",
        key=f"mic_{day}",
    )

    # 新しい音声入力があった場合、既存のテキストに「追記」する
    if spoken_text and spoken_text != st.session_state[f"last_spoken_{day}"]:
      current_text = st.session_state[f"input_text_{day}"]
      if current_text.strip():
        # すでに文字がある場合はスペースを空けて後ろに追加
        st.session_state[f"input_text_{day}"] = (
            current_text.strip() + " " + spoken_text
        )
      else:
        # 空っぽの場合はそのまま代入
        st.session_state[f"input_text_{day}"] = spoken_text

      st.session_state[f"last_spoken_{day}"] = spoken_text
      st.rerun()

    # ディクテーション入力欄（手動修正も保持されます）
    user_input = st.text_area(
        "入力されたテキスト（手動で修正もできます）：",
        key=f"input_text_{day}",
        height=180,
        placeholder="ここに音声入力のテキストが反映されます...",
    )

    btn_col1, btn_col2 = st.columns(2)
    submit_btn = btn_col1.button(
        "答え合わせ ＆ 記録", type="primary", use_container_width=True
    )
    show_trans_btn = btn_col2.button(
        "日本語訳を表示 🇯🇵", use_container_width=True
    )

  with col_right:
    st.subheader("結果確認")
    raw_text = transcripts.get(day, "")
    correct_text, japanese_text = parse_transcript_entry(raw_text)

    if show_trans_btn:
      st.info(f"**🇯🇵 Day {day} の日本語訳:**\n\n{japanese_text}")

    if submit_btn:
      if not correct_text:
        st.error(f"Day {day} のテキストデータが見つかりません。")
      else:
        orig_words = clean_text(correct_text)
        user_words = clean_text(user_input)
        matcher = difflib.SequenceMatcher(None, orig_words, user_words)

        missing_words, misheard_words = [], []
        equal_count = 0
        result_html = ""

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
          orig_str = " ".join(orig_words[i1:i2])
          user_str = " ".join(user_words[j1:j2])
          if tag == "equal":
            result_html += (
                f"<span style='color: #15803d; font-weight:"
                f" bold;'>{orig_str}</span> "
            )
            equal_count += i2 - i1
          elif tag == "delete":
            result_html += (
                "<span style='color: #b91c1c; background-color: #fee2e2;"
                f" padding: 2px 4px; border-radius: 3px;'>[聞き逃し:"
                f" {orig_str}]</span> "
            )
            missing_words.extend(orig_words[i1:i2])
          elif tag == "insert":
            result_html += (
                f"<span style='color: #1d4ed8;"
                f" text-decoration: line-through;'>{user_str}</span> "
            )
          elif tag == "replace":
            result_html += (
                f"<span style='color: #b91c1c; font-weight:"
                f" bold;'>{orig_str}</span> <span style='color: #1d4ed8;'>(入力:"
                f" {user_str})</span> "
            )
            misheard_words.extend(orig_words[i1:i2])

        total_words = len(orig_words)
        accuracy = (
            round((equal_count / total_words * 100), 1)
            if total_words > 0
            else 0
        )

        st.markdown(
            f"### 正解率: **{accuracy}%** ({equal_count} / {total_words} 単語)"
        )
        st.markdown(f"**判定:** {result_html}", unsafe_allow_html=True)
        st.markdown(f"**原文:** {correct_text}")
        if japanese_text and "データなし" not in japanese_text:
          st.markdown(f"**和訳:** {japanese_text}")

        # CSVへの履歴保存
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "day": day,
            "accuracy": accuracy,
            "correct_words": equal_count,
            "total_words": total_words,
            "missing_words": ",".join(missing_words),
            "misheard_words": ",".join(misheard_words),
        }
        df_new = pd.DataFrame([log_entry])
        df_new.to_csv(
            CSV_PATH,
            mode="a" if os.path.exists(CSV_PATH) else "w",
            header=not os.path.exists(CSV_PATH),
            index=False,
            encoding="utf-8-sig",
        )
        st.success("💾 学習記録を保存しました！")

# --- TAB 2: 弱点分析レポート ---
with tab2:
  st.header("📊 弱点分析レポート")
  if os.path.exists(CSV_PATH):
    df = pd.read_csv(CSV_PATH)
    if len(df) > 0:
      m1, m2, m3 = st.columns(3)
      m1.metric("総学習回数", f"{len(df)} 回")
      m2.metric("平均正解率", f"{round(df['accuracy'].mean(), 1)} %")

      missing_words, misheard_words = [], []
      for item in df["missing_words"].dropna():
        if str(item).strip():
          missing_words.extend(str(item).split(","))
      for item in df["misheard_words"].dropna():
        if str(item).strip():
          misheard_words.extend(str(item).split(","))

      all_missed = missing_words + misheard_words
      m3.metric("総エラー単語数", f"{len(all_missed)} 語")

      if all_missed:
        st.subheader("🔥 よく間違える単語 TOP 10")
        counts = Counter(all_missed)
        top_df = pd.DataFrame(
            counts.most_common(10), columns=["単語", "ミス回数"]
        )
        st.table(top_df)
  else:
    st.info(
        "まだ学習履歴がありません。ディクテーションを行うとレポートが表示されます。"
    )
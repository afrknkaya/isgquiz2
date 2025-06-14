import streamlit as st
import docx  # DOCX dosyalarını okumak için
import re
import os # Dosya kontrolü için
import time # sleep için
import random # Soruları karıştırmak için

# Dosya yolları doğrudan burada belirtiliyor, kullanıcı yüklemeyecek.
QUESTIONS_FILE = "sorular.docx"
ANSWERS_FILE = "cevaplar.txt"

# DOCX dosyasından soruları ayrıştırma fonksiyonu
@st.cache_data
def parse_questions_from_docx(file_path):
    """
    Belirtilen DOCX dosya yolundan soru numarasını, metnini ve şıklarını ayrıştırır.
    Soru formatı: "501.Soru metni..."
    Şık formatı: "A. Şık metni"
    """
    if not os.path.exists(file_path):
        st.error(f"Sorular dosyası bulunamadı: {file_path}")
        return []

    doc = docx.Document(file_path)
    
    # Tüm non-empty satırları al, boşlukları temizle ve daha robust hale getir
    lines_content = []
    for para in doc.paragraphs:
        stripped_line = para.text.strip()
        if stripped_line:
            # Birden fazla boşluğu tek boşluğa indir ve uçlardaki boşlukları temizle
            cleaned_line = re.sub(r'\s+', ' ', stripped_line).strip()
            lines_content.append(cleaned_line)

    questions = []
    current_question = None
    
    # Soru numarasını ve metnini yakalar (örn: "501.Yapı işlerinde...")
    # Soru numarası ve noktadan hemen sonra gelen metin.
    question_pattern = re.compile(r"^\s*(\d+)\.(.*)", re.DOTALL)
    
    # Şık harfini, noktayı, isteğe bağlı boşlukları ve şık metnini yakalar (örn: "A. 80")
    option_pattern = re.compile(r"^\s*([A-D])\.\s*(.*)", re.IGNORECASE) 

    i = 0
    while i < len(lines_content):
        line = lines_content[i]

        # "TEST" başlıklarını atla
        if line.startswith("TEST") and line[4:].strip().isdigit():
            i += 1
            continue

        # Soru başlangıcını kontrol et
        q_match = question_pattern.match(line)
        if q_match:
            # Önceki soruyu kaydet
            if current_question:
                questions.append(current_question)

            # Yeni soruyu başlat
            question_number = q_match.group(1)
            # Soru metninin başlangıcı, numara ve nokta hariç
            question_text = q_match.group(2).strip() 
            current_question = {
                "number": question_number,
                "question": question_text,
                "options": [],
            }
            i += 1
            
            # Çok satırlı soru metnini yakala (şıklar veya yeni soru başlamadan önce)
            while i < len(lines_content) and \
                  not option_pattern.match(lines_content[i]) and \
                  not question_pattern.match(lines_content[i]) and \
                  not (lines_content[i].startswith("TEST") and lines_content[i][4:].strip().isdigit()):
                
                current_question["question"] += " " + lines_content[i].strip()
                i += 1
            continue

        # Şık hattıyla eşleşirse
        opt_match = option_pattern.match(line)
        if opt_match and current_question:
            # Şık metnini doğrudan yakalayıp ekle
            current_question["options"].append(line)
            i += 1 # Şık metnini tükettik, bir sonraki satıra geç
            continue
        
        # Eğer mevcut satır ne bir soru ne de bir şık hattı ise, bir sonraki satıra geç
        # Bu, ayrıştırma esnasında gözden kaçan veya format dışı satırları atlamamızı sağlar.
        i += 1

    # Döngü bittiğinde son soruyu listeye ekle
    if current_question:
        questions.append(current_question)

    return questions

# TXT dosyasından doğru cevapları ayrıştırma fonksiyonu
@st.cache_data
def parse_correct_answers_from_txt(file_path):
    """
    Belirtilen TXT dosya yolundan soru numarası ve doğru cevap eşleştirmesini ayrıştırır.
    Format: '500: A'
    """
    if not os.path.exists(file_path):
        st.error(f"Cevaplar dosyası bulunamadı: {file_path}")
        return {}

    correct_answers = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(':')
            if len(parts) == 2:
                question_number = parts[0].strip()
                answer_letter = parts[1].strip().lower()
                correct_answers[question_number] = answer_letter
    return correct_answers

# --- on_change callback fonksiyonu ---
# Bu fonksiyon, st.radio bileşeni her değiştiğinde çağrılır.
def handle_option_change(questions, correct_answers):
    current_q_key = f"q{st.session_state.index}"
    selected_option = st.session_state[current_q_key] # Seçilen şıkkın metni

    question_num = questions[st.session_state.index]['number']
    selected_letter = selected_option[0].lower().strip().replace('\ufeff', '')
    
    correct_answer = correct_answers.get(question_num, None)
    correct_answer_cleaned = None
    if correct_answer:
        correct_answer_cleaned = correct_answer.strip().lower().replace('\ufeff', '')

    current_correctness = (selected_letter == correct_answer_cleaned) if correct_answer_cleaned else None

    # Kullanıcının mevcut cevabını oturuma kaydet
    st.session_state.user_answers[question_num] = selected_letter
    
    # Sınav modunda değilsek (Alıştırma Modu)
    if not st.session_state.exam_mode_active:
        # Sadece ilk deneme ise first_attempt_statuses'ı güncelle
        if question_num not in st.session_state.first_attempt_statuses:
            st.session_state.first_attempt_statuses[question_num] = current_correctness
        
        # question_statuses (anlık durum) her zaman güncellenir
        st.session_state.question_statuses[question_num] = current_correctness

        # Doğru/Yanlış sayılarını mevcut question_statuses'a göre yeniden hesapla
        st.session_state.correct_count = sum(1 for status in st.session_state.question_statuses.values() if status is True)
        st.session_state.incorrect_count = sum(1 for status in st.session_state.question_statuses.values() if status is False)

        # Geri bildirim tetikleyicisini ayarla (Alıştırma Modu için)
        if correct_answer_cleaned is None:
            st.session_state.feedback_trigger = 'no_answer_found'
        elif current_correctness: # Doğru cevap
            st.session_state.feedback_trigger = 'correct'
        else: # Yanlış cevap
            st.session_state.feedback_trigger = 'incorrect'
    else: # Sınav modunda ise
        # Sınav modunda her soruya bir kez cevap verilebilir
        st.session_state.exam_answers[question_num] = selected_letter # Sınav cevaplarını kaydet
        st.session_state.questions_answered_in_exam[question_num] = True # Sorunun cevaplandığını işaretler

    st.rerun() # UI'ı güncellemek için yeniden çalıştır


def main():
    st.set_page_config(layout="wide", page_title="İSG Sınav Uygulaması")

    st.title("İSG Sınav Uygulaması")
    st.markdown("---")

    questions_full_list = [] # Tüm soruların listesi
    correct_answers = {}

    try:
        with st.spinner("Sorular yükleniyor ve ayrıştırılıyor..."):
            questions_full_list = parse_questions_from_docx(QUESTIONS_FILE)
        if not questions_full_list:
            st.error(f"Sorular '{QUESTIONS_FILE}' dosyasından ayrıştırılamadı veya dosya boş. Formatı kontrol edin.")
            st.stop() # Uygulamayı durdur
    except Exception as e:
        st.error(f"Sorular dosyası okunurken bir hata oluştu: {e}. Dosyanın bozuk olmadığından emin olun.")
        st.stop()

    try:
        with st.spinner("Cevaplar yükleniyor ve ayrıştırılıyor..."):
            correct_answers = parse_correct_answers_from_txt(ANSWERS_FILE)
        if not correct_answers:
            st.error(f"Cevaplar '{ANSWERS_FILE}' dosyasından ayrıştırılamadı veya dosya boş. Formatı kontrol edin.")
            st.stop() # Uygulamayı durdur
    except Exception as e:
        st.error(f"Cevaplar dosyası okunurken bir hata oluştu: {e}. Dosyanın bozuk olmadığından emin olun.")
        st.stop()

    # Oturum durumu başlatma
    if "index" not in st.session_state:
        st.session_state.index = 0
    if "user_answers" not in st.session_state: 
        st.session_state.user_answers = {}
    if "question_statuses" not in st.session_state: 
        st.session_state.question_statuses = {} 
    if "first_attempt_statuses" not in st.session_state: 
        st.session_state.first_attempt_statuses = {} 
    if "correct_count" not in st.session_state: 
        st.session_state.correct_count = 0
    if "incorrect_count" not in st.session_state: 
        st.session_state.incorrect_count = 0
    if "feedback_trigger" not in st.session_state: 
        st.session_state.feedback_trigger = None
    if "review_mode_active" not in st.session_state: 
        st.session_state.review_mode_active = False
    if "current_question_list" not in st.session_state: 
        st.session_state.current_question_list = questions_full_list # Başlangıçta tüm sorular
    if "prev_index" not in st.session_state: 
        st.session_state.prev_index = st.session_state.index

    # --- Sınav Modu için Yeni Oturum Değişkenleri ---
    if "exam_mode_active" not in st.session_state:
        st.session_state.exam_mode_active = False # Varsayılan: Alıştırma Modu
    if "exam_submitted" not in st.session_state:
        st.session_state.exam_submitted = False # Sınav bitirildi mi?
    if "exam_answers" not in st.session_state:
        st.session_state.exam_answers = {} # Sınav modundaki kullanıcının cevapları
    if "questions_answered_in_exam" not in st.session_state:
        st.session_state.questions_answered_in_exam = {} # Sınav modunda cevaplanan soruları işaretler
    if "exam_results" not in st.session_state:
        st.session_state.exam_results = None # Sınav sonuçları
    # Yeni eklendi: Sınav sonrası yanlışları inceleme modu
    if "review_exam_incorrect_active" not in st.session_state:
        st.session_state.review_exam_incorrect_active = False
    if "exam_incorrect_questions_for_review" not in st.session_state: # Sınavda yanlış yapılan sorular
        st.session_state.exam_incorrect_questions_for_review = []


    # Eğer soru değiştiyse feedback'i sıfırla
    if st.session_state.index != st.session_state.prev_index:
        st.session_state.feedback_trigger = None
        st.session_state.prev_index = st.session_state.index

    # --- Mod Seçimi ---
    st.sidebar.header("Mod Seçimi")
    mode = st.sidebar.radio(
        "Lütfen bir mod seçin:",
        ("Alıştırma Modu", "Sınav Modu"),
        key="mode_selection",
        index=0 if not st.session_state.exam_mode_active else 1 # Modu session state'e göre ayarla
    )

    if mode == "Sınav Modu" and not st.session_state.exam_mode_active:
        # Sınav moduna geçiş yapılıyorsa durumu sıfırla ve soruları karıştır
        st.session_state.exam_mode_active = True
        st.session_state.exam_submitted = False
        st.session_state.exam_answers = {}
        st.session_state.questions_answered_in_exam = {}
        st.session_state.exam_results = None
        st.session_state.index = 0
        st.session_state.feedback_trigger = None # Mesajı temizle
        st.session_state.review_exam_incorrect_active = False # Sınav inceleme modunu kapat

        # Rastgele 20 soru seç (veya toplam soru sayısı 20'den azsa hepsini)
        num_exam_questions = min(20, len(questions_full_list))
        st.session_state.current_question_list = random.sample(questions_full_list, num_exam_questions)
        st.rerun() # Mod değişikliğini uygulamak için yeniden çalıştır
    elif mode == "Alıştırma Modu" and st.session_state.exam_mode_active:
        # Alıştırma moduna geçiş yapılıyorsa durumu sıfırla ve tüm sorulara dön
        st.session_state.exam_mode_active = False
        st.session_state.exam_submitted = False
        st.session_state.exam_answers = {}
        st.session_state.questions_answered_in_exam = {}
        st.session_state.exam_results = None
        st.session_state.index = 0
        st.session_state.feedback_trigger = None # Mesajı temizle
        st.session_state.user_answers = {} # Alıştırma modu cevaplarını temizle
        st.session_state.question_statuses = {} # Alıştırma modu durumlarını temizle
        st.session_state.first_attempt_statuses = {} # İlk deneme durumlarını temizle
        st.session_state.correct_count = 0
        st.session_state.incorrect_count = 0
        st.session_state.review_exam_incorrect_active = False # Sınav inceleme modunu kapat

        st.session_state.current_question_list = questions_full_list
        st.rerun() # Mod değişikliğini uygulamak için yeniden çalıştır

    # --- Sınav Sonuçları Ekranı ---
    # Bu blok, sadece sınav modundayken ve sınav bitirildiğinde çalışır.
    # review_exam_incorrect_active true ise bu bloğa girilmez, question display bloğuna gidilir.
    if st.session_state.exam_mode_active and st.session_state.exam_submitted and not st.session_state.review_exam_incorrect_active:
        st.header("Sınav Sonuçlarınız")
        if st.session_state.exam_results:
            results = st.session_state.exam_results
            st.metric(label="Doğru Cevap Sayısı", value=results['correct'])
            st.metric(label="Yanlış Cevap Sayısı", value=results['incorrect'])
            st.metric(label="Boş Bırakılan Soru Sayısı", value=results['unanswered'])
            st.metric(label="Başarı Yüzdesi", value=f"{results['percentage']:.2f}%")
            
            # Yanlışları inceleme butonu
            # Sadece yanlış cevaplanan soru varsa göster
            if st.session_state.exam_incorrect_questions_for_review:
                if st.sidebar.button("Yanlış Cevapları İncele", key="review_exam_incorrect_button"):
                    st.session_state.review_exam_incorrect_active = True
                    st.session_state.current_question_list = st.session_state.exam_incorrect_questions_for_review
                    st.session_state.index = 0 # İlk yanlış soruya git
                    st.session_state.feedback_trigger = None # Mesajı temizle
                    st.rerun()
            else:
                st.sidebar.info("Tebrikler! Bu sınavda yanlış cevabınız yok.")

            if st.sidebar.button("Yeni Sınav Başlat", key="new_exam_button_results"):
                st.session_state.exam_mode_active = True # Zaten sınav modunda kal
                st.session_state.exam_submitted = False
                st.session_state.exam_answers = {}
                st.session_state.questions_answered_in_exam = {}
                st.session_state.exam_results = None
                st.session_state.index = 0
                st.session_state.feedback_trigger = None
                st.session_state.review_exam_incorrect_active = False # Sınav inceleme modunu kapat
                st.session_state.exam_incorrect_questions_for_review = [] # Yanlış listesini temizle

                num_exam_questions = min(20, len(questions_full_list))
                st.session_state.current_question_list = random.sample(questions_full_list, num_exam_questions)
                st.rerun()
            
            st.sidebar.markdown("---")
            st.sidebar.header("Sınav Cevaplarınızın Detayı")
            for q_idx, q_exam in enumerate(st.session_state.current_question_list):
                q_num = q_exam['number']
                user_ans = st.session_state.exam_answers.get(q_num, "Boş")
                
                correct_ans = correct_answers.get(q_num, None)
                correct_ans_cleaned = correct_ans.strip().upper() if correct_ans else "Yok"
                
                user_ans_display = user_ans.upper() if user_ans != "Boş" else "Boş"

                status_emoji = "❓"
                if user_ans != "Boş":
                    if user_ans.lower() == correct_ans_cleaned.lower():
                        status_emoji = "✅"
                    else:
                        status_emoji = "❌"
                
                st.sidebar.markdown(f"**{q_idx + 1}. ({q_num}):** Seçim: {user_ans_display} | Doğru: {correct_ans_cleaned} {status_emoji}")
            
        return # Sınav bitince ve inceleme modunda değilken diğer UI öğelerini gösterme

    # questions değişkenini her zaman güncel tut
    questions = st.session_state.current_question_list
    question_count = len(questions)


    # Soru atlama mekanizması
    st.markdown("---")
    col_jump1, col_jump2, col_jump3 = st.columns([2, 1, 2])
    with col_jump1:
        jump_number = st.number_input(
            "Gitmek İstediğiniz Soru Numarası:",
            min_value=1,
            max_value=question_count,
            value=st.session_state.index + 1,
            key="jump_input"
        )
    with col_jump2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Atla", key="jump_button"):
            new_index = jump_number - 1
            if 0 <= new_index < question_count:
                st.session_state.index = new_index
                st.rerun()

    # Navigasyon butonları
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    with col_nav1:
        # Sadece indeks 0'daysa "Geri" butonu devre dışı kalır
        if st.button("⟵ Geri", key="prev_button", disabled=st.session_state.index <= 0) and st.session_state.index > 0:
            st.session_state.index -= 1
            st.rerun()
    with col_nav3:
        # Sadece son sorudaysa "İleri" butonu devre dışı kalır
        if st.button("İleri ⟶", key="next_button", disabled=st.session_state.index >= question_count - 1) and st.session_state.index < question_count - 1:
            st.session_state.index += 1
            st.rerun()

    st.markdown("---")

    # Mevcut soruyu göster
    if questions: 
        soru = questions[st.session_state.index]
        
        # Soru başlığı ve metnini moda göre farklı şekilde göster
        # Soru numarası her zaman görünmeli
        st.subheader(f"{st.session_state.index + 1}. Soru (Soru No: {soru['number']})") 
        
        # Soru metnini ise moda göre biçimlendir
        if st.session_state.review_exam_incorrect_active:
            st.markdown(f"### **{soru['question']}**") # Soru metnini daha büyük ve kalın yap
        else:
            st.markdown(f"**{soru['question']}**")

        feedback_message_area = st.empty()

        pre_selected_index = None
        # Eğer Alıştırma modundaysak ve kontrol modunda değilsek, daha önce verilen cevabı ön seçili getir
        if not st.session_state.exam_mode_active and not st.session_state.review_mode_active and soru["number"] in st.session_state.user_answers:
            for i, opt_text in enumerate(soru['options']):
                if opt_text and len(opt_text) > 0 and opt_text[0].lower() == st.session_state.user_answers[soru["number"]]:
                    pre_selected_index = i
                    break
        # Sınav modundaysak (veya sınav inceleme modundaysak), ilgili cevabı ön seçili getir
        elif st.session_state.exam_mode_active and (soru["number"] in st.session_state.exam_answers):
             # Sınav modunda veya sınav inceleme modunda aynı mantığı kullan
             for i, opt_text in enumerate(soru['options']):
                if opt_text and len(opt_text) > 0 and opt_text[0].lower() == st.session_state.exam_answers[soru["number"]]:
                    pre_selected_index = i
                    break

        # Şıklar devre dışı bırakılacak mı?
        # Sınav modunda cevaplandıysa VEYA sınav inceleme modundaysak devre dışı
        is_radio_disabled = (st.session_state.exam_mode_active and st.session_state.questions_answered_in_exam.get(soru['number'], False)) or \
                            st.session_state.review_exam_incorrect_active

        selected_option = st.radio(
            "Şıkları seçin:",
            soru['options'],
            key=f"q{st.session_state.index}", 
            index=pre_selected_index, 
            on_change=handle_option_change, 
            args=(questions, correct_answers),
            disabled=is_radio_disabled # Şıkları devre dışı bırak
        )

        # Sınav inceleme modunda ekstra bilgi göster (şimdi sadece cevapları gösterecek)
        if st.session_state.review_exam_incorrect_active:
            st.markdown("---") # Ayırıcı çizgi
            user_ans = st.session_state.exam_answers.get(soru['number'], "Boş")
            correct_ans = correct_answers.get(soru['number'], None)
            correct_ans_display = correct_ans.upper() if correct_ans else "Yok"
            
            st.markdown(f"**Sizin Cevabınız:** {user_ans.upper() if user_ans != 'Boş' else 'Boş'} {'❌' if user_ans and user_ans.lower() != correct_ans.lower() else ''}")
            st.markdown(f"**Doğru Cevap:** {correct_ans_display} ✅")
            st.markdown(f"---")
            
            if st.button("Sınav Sonuçlarına Geri Dön", key="back_to_exam_results_review"):
                st.session_state.review_exam_incorrect_active = False
                st.session_state.exam_submitted = True # Tekrar sonuç ekranına dön
                st.session_state.index = 0 # İndeksi sıfırla, sonuç ekranı tekrar yüklenecek
                st.rerun()

        # Geri bildirim mesajları (Sadece Alıştırma Modu için aktif)
        if not st.session_state.exam_mode_active and not st.session_state.review_exam_incorrect_active:
            if st.session_state.feedback_trigger == 'correct':
                feedback_message_area.success("✅ Doğru cevap!")
                time.sleep(1) 
                
                if st.session_state.index < question_count - 1:
                    st.session_state.index += 1
                    st.session_state.feedback_trigger = None 
                    st.rerun() 
                else:
                    st.balloons() 
                    feedback_message_area.success("Tebrikler, tüm soruları bitirdiniz!")
                    st.session_state.feedback_trigger = None 

            elif st.session_state.feedback_trigger == 'incorrect':
                feedback_message_area.error("❌ Yanlış cevap!") 
            
            elif st.session_state.feedback_trigger == 'no_answer_found':
                feedback_message_area.warning(f"Soru {soru['number']} için doğru cevap bulunamadı. Lütfen cevaplar.txt dosyasını kontrol edin.")
                st.session_state.feedback_trigger = None 
            else: 
                feedback_message_area.empty()
        
        # --- Sınav Modu Otomatik İlerleme ---
        # Sınav modundayız, mevcut soru cevaplandı mı ve henüz son soru değil mi?
        # Ve sınav inceleme modunda değilsek
        if st.session_state.exam_mode_active and \
           st.session_state.questions_answered_in_exam.get(soru['number'], False) and \
           st.session_state.index < question_count - 1 and \
           not st.session_state.review_exam_incorrect_active: 
            
            feedback_message_area.empty() # Sınav modunda anlık metinsel mesaj göstermiyoruz
            time.sleep(1) # Kullanıcının istediği 1 saniye bekleme
            st.session_state.index += 1 # Bir sonraki soruya geç
            st.rerun() # Yeni soruyu yükle ve UI'ı güncelle

        # Sınavı Bitir butonu (Sınav modunda ve son sorudaysak veya tüm sorular cevaplanmışsa)
        if st.session_state.exam_mode_active and \
           not st.session_state.review_exam_incorrect_active and \
           (st.session_state.index == question_count - 1 or len(st.session_state.questions_answered_in_exam) == question_count):
            if st.button("Sınavı Bitir", key="submit_exam_button"):
                # Sınav sonuçlarını hesapla
                exam_correct = 0
                exam_incorrect = 0
                exam_unanswered = 0
                
                st.session_state.exam_incorrect_questions_for_review = [] # Her sınav bitişinde sıfırla

                for q_exam in st.session_state.current_question_list:
                    q_num = q_exam['number']
                    user_ans = st.session_state.exam_answers.get(q_num, None)
                    correct_ans = correct_answers.get(q_num, None)
                    
                    if user_ans is None:
                        exam_unanswered += 1
                    elif correct_ans and user_ans.lower().strip().replace('\ufeff', '') == correct_ans.lower().strip().replace('\ufeff', ''):
                        exam_correct += 1
                    else:
                        exam_incorrect += 1
                        st.session_state.exam_incorrect_questions_for_review.append(q_exam) # Yanlış yapılanı listeye ekle
                
                total_questions = len(st.session_state.current_question_list)
                percentage = (exam_correct / total_questions) * 100 if total_questions > 0 else 0

                st.session_state.exam_results = {
                    "correct": exam_correct,
                    "incorrect": exam_incorrect,
                    "unanswered": exam_unanswered,
                    "percentage": percentage
                }
                st.session_state.exam_submitted = True
                st.rerun() # Sonuçları göstermek için yeniden çalıştır

    else: # questions listesi boşsa
        st.info("Gösterilecek soru bulunmuyor. Lütfen dosya yükleyin veya 'Tüm Sorulara Dön' butonunu kullanın.")


    # İlerleme çubuğu
    st.markdown("---")
    current_progress_display = st.session_state.index + 1
    if st.session_state.exam_mode_active and not st.session_state.exam_submitted: # Sınav modundayız ve henüz bitmedi
        answered_count = len(st.session_state.questions_answered_in_exam)
        progress_percentage = answered_count / question_count if question_count > 0 else 0
        st.caption(f"**Cevaplanan Soru: {answered_count}/{question_count}**")
        progress_bar_value = progress_percentage
    elif st.session_state.review_exam_incorrect_active: # Sınav yanlışlarını inceleme modundayız
        st.caption(f"**Yanlış İnceleme: {st.session_state.index + 1}/{question_count}**")
        progress_bar_value = (st.session_state.index + 1) / question_count
    else: # Alıştırma Modu veya Sınav bitmişse
        progress_bar_value = (st.session_state.index + 1) / question_count
        st.caption(f"**İlerleme: {st.session_state.index + 1}/{question_count}**")

    progress = st.progress(progress_bar_value)


    # Genel İstatistikler (Moda göre değişir)
    st.sidebar.markdown("---")
    st.sidebar.header("İstatistikler")
    
    if st.session_state.exam_mode_active and not st.session_state.exam_submitted:
        st.sidebar.info(f"**Cevaplanan Soru:** {len(st.session_state.questions_answered_in_exam)}/{question_count}")
    elif st.session_state.exam_mode_active and st.session_state.exam_submitted: # Sınav bitmişse ve sonuçlar gösteriliyorsa
        st.sidebar.info(f"**Toplam Doğru:** {st.session_state.exam_results['correct'] if st.session_state.exam_results else 0}")
        st.sidebar.warning(f"**Toplam Yanlış:** {st.session_state.exam_results['incorrect'] if st.session_state.exam_results else 0}")
        st.sidebar.error(f"**Boş:** {st.session_state.exam_results['unanswered'] if st.session_state.exam_results else 0}")
    else: # Alıştırma Modu
        st.sidebar.info(f"**Doğru Cevaplar (Anlık):** {st.session_state.correct_count}")
        st.sidebar.warning(f"**Yanlış Cevaplar (Anlık):** {st.session_state.incorrect_count}")
        
        st.sidebar.markdown("---")
        # Kontrol Modu Butonları (Sadece Alıştırma Modunda)
        if not st.session_state.review_mode_active:
            if st.sidebar.button("İlk Denemede Yanlış Yapılanları Kontrol Et", key="review_button"):
                incorrect_questions_for_review = [
                    q for q in questions_full_list 
                    if st.session_state.first_attempt_statuses.get(q["number"]) is False
                ]
                if not incorrect_questions_for_review:
                    st.sidebar.success("Tebrikler! İlk denemede yanlış cevapladığınız soru yok.")
                    st.session_state.review_mode_active = False 
                else:
                    st.session_state.review_mode_active = True
                    st.session_state.current_question_list = incorrect_questions_for_review
                    st.session_state.index = 0 
                    st.session_state.feedback_trigger = None 
                    st.rerun()
        else: # review_mode_active True ise
            if st.sidebar.button("Tüm Sorulara Geri Dön", key="exit_review_button"):
                st.session_state.review_mode_active = False
                st.session_state.current_question_list = questions_full_list
                st.session_state.index = 0 
                st.session_state.feedback_trigger = None 
                st.rerun()

        st.sidebar.markdown("---")
        st.sidebar.header("Cevap Durumları (İlk Deneme)")
        # Cevaplanmış soruları ve durumlarını göster (ilk denemeye göre, sadece Alıştırma Modunda)
        for i, q_full in enumerate(questions_full_list): 
            first_attempt_status = st.session_state.first_attempt_statuses.get(q_full["number"])
            
            if first_attempt_status is not None: 
                status_emoji = "✅" if first_attempt_status is True else "❌"
                st.sidebar.write(f"{i + 1}. Soru ({q_full['number']}): {status_emoji}")
            else: 
                st.sidebar.write(f"{i + 1}. Soru ({q_full['number']}): ⚪") 

if __name__ == "__main__":
    main()

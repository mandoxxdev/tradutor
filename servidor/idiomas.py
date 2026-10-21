"""
Tabela de idiomas suportados.

Cada idioma tem:
  codigo      - código usado internamente (ISO 639-1; "zh_Hant" e "yue" são variantes)
  whisper     - código que o Whisper reconhece (o chinês tradicional usa "zh")
  nome_pt     - nome em português (sempre exibido)
  nome_nativo - nome no próprio idioma (exibido ao lado)
  nllb        - código do NLLB-200
  argos       - código do Argos Translate (None = Argos não tem pacote)
  bcp47       - código para o atributo lang="" do HTML (escolha de fonte no navegador)
  rtl         - True para escrita da direita para a esquerda
  prompt      - frase curta usada como "initial_prompt" do Whisper (opcional)

Só entram aqui idiomas que o Whisper E o NLLB-200 suportam.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Idioma:
    codigo: str
    whisper: str
    nome_pt: str
    nome_nativo: str
    nllb: str
    argos: str | None = None
    bcp47: str | None = None
    rtl: bool = False
    prompt: str | None = None

    @property
    def rotulo(self) -> str:
        """Ex.: 'ITALIANO · Italiano' / 'CHINÊS (SIMPLIFICADO) · 中文（简体）'."""
        return f"{self.nome_pt.upper()} · {self.nome_nativo}"

    def para_json(self) -> dict:
        return {
            "codigo": self.codigo,
            "nome_pt": self.nome_pt,
            "nome_nativo": self.nome_nativo,
            "rotulo": self.rotulo,
            "bcp47": self.bcp47 or self.codigo,
            "rtl": self.rtl,
            "argos": self.argos is not None,
        }


PORTUGUES = "pt"

# (codigo, whisper, nome_pt, nome_nativo, nllb, argos, bcp47, rtl, prompt)
_TABELA = [
    ("pt", "pt", "Português", "Português do Brasil", "por_Latn", "pt", "pt-BR", False, None),
    ("en", "en", "Inglês", "English", "eng_Latn", "en", "en", False, None),
    ("es", "es", "Espanhol", "Español", "spa_Latn", "es", "es", False, None),
    ("it", "it", "Italiano", "Italiano", "ita_Latn", "it", "it", False, None),
    ("de", "de", "Alemão", "Deutsch", "deu_Latn", "de", "de", False, None),
    ("fr", "fr", "Francês", "Français", "fra_Latn", "fr", "fr", False, None),
    ("zh", "zh", "Chinês (simplificado)", "中文（简体）", "zho_Hans", "zh", "zh-Hans", False, "以下是普通话的句子。"),
    ("zh_Hant", "zh", "Chinês (tradicional)", "中文（繁體）", "zho_Hant", "zt", "zh-Hant", False, "以下是普通話的句子。"),
    ("yue", "yue", "Cantonês", "粵語", "yue_Hant", None, "yue", False, None),
    ("ja", "ja", "Japonês", "日本語", "jpn_Jpan", "ja", "ja", False, None),
    ("ko", "ko", "Coreano", "한국어", "kor_Hang", "ko", "ko", False, None),
    ("ru", "ru", "Russo", "Русский", "rus_Cyrl", "ru", "ru", False, None),
    ("ar", "ar", "Árabe", "العربية", "arb_Arab", "ar", "ar", True, None),
    ("he", "he", "Hebraico", "עברית", "heb_Hebr", "he", "he", True, None),
    ("fa", "fa", "Persa", "فارسی", "pes_Arab", "fa", "fa", True, None),
    ("ur", "ur", "Urdu", "اردو", "urd_Arab", "ur", "ur", True, None),
    ("ps", "ps", "Pachto", "پښتو", "pbt_Arab", None, "ps", True, None),
    ("sd", "sd", "Sindi", "سنڌي", "snd_Arab", None, "sd", True, None),
    ("yi", "yi", "Iídiche", "ייִדיש", "ydd_Hebr", None, "yi", True, None),
    ("hi", "hi", "Hindi", "हिन्दी", "hin_Deva", "hi", "hi", False, None),
    ("bn", "bn", "Bengali", "বাংলা", "ben_Beng", "bn", "bn", False, None),
    ("tr", "tr", "Turco", "Türkçe", "tur_Latn", "tr", "tr", False, None),
    ("pl", "pl", "Polonês", "Polski", "pol_Latn", "pl", "pl", False, None),
    ("nl", "nl", "Holandês", "Nederlands", "nld_Latn", "nl", "nl", False, None),
    ("sv", "sv", "Sueco", "Svenska", "swe_Latn", "sv", "sv", False, None),
    ("da", "da", "Dinamarquês", "Dansk", "dan_Latn", "da", "da", False, None),
    ("no", "no", "Norueguês (bokmål)", "Norsk bokmål", "nob_Latn", "nb", "nb", False, None),
    ("nn", "nn", "Norueguês (nynorsk)", "Nynorsk", "nno_Latn", None, "nn", False, None),
    ("fi", "fi", "Finlandês", "Suomi", "fin_Latn", "fi", "fi", False, None),
    ("is", "is", "Islandês", "Íslenska", "isl_Latn", None, "is", False, None),
    ("el", "el", "Grego", "Ελληνικά", "ell_Grek", "el", "el", False, None),
    ("cs", "cs", "Tcheco", "Čeština", "ces_Latn", "cs", "cs", False, None),
    ("sk", "sk", "Eslovaco", "Slovenčina", "slk_Latn", "sk", "sk", False, None),
    ("hu", "hu", "Húngaro", "Magyar", "hun_Latn", "hu", "hu", False, None),
    ("ro", "ro", "Romeno", "Română", "ron_Latn", "ro", "ro", False, None),
    ("bg", "bg", "Búlgaro", "Български", "bul_Cyrl", "bg", "bg", False, None),
    ("uk", "uk", "Ucraniano", "Українська", "ukr_Cyrl", "uk", "uk", False, None),
    ("be", "be", "Bielorrusso", "Беларуская", "bel_Cyrl", None, "be", False, None),
    ("sr", "sr", "Sérvio", "Српски", "srp_Cyrl", None, "sr", False, None),
    ("hr", "hr", "Croata", "Hrvatski", "hrv_Latn", None, "hr", False, None),
    ("bs", "bs", "Bósnio", "Bosanski", "bos_Latn", None, "bs", False, None),
    ("sl", "sl", "Esloveno", "Slovenščina", "slv_Latn", "sl", "sl", False, None),
    ("mk", "mk", "Macedônio", "Македонски", "mkd_Cyrl", None, "mk", False, None),
    ("sq", "sq", "Albanês", "Shqip", "als_Latn", "sq", "sq", False, None),
    ("lt", "lt", "Lituano", "Lietuvių", "lit_Latn", "lt", "lt", False, None),
    ("lv", "lv", "Letão", "Latviešu", "lvs_Latn", "lv", "lv", False, None),
    ("et", "et", "Estoniano", "Eesti", "est_Latn", "et", "et", False, None),
    ("ca", "ca", "Catalão", "Català", "cat_Latn", "ca", "ca", False, None),
    ("gl", "gl", "Galego", "Galego", "glg_Latn", "gl", "gl", False, None),
    ("eu", "eu", "Basco", "Euskara", "eus_Latn", "eu", "eu", False, None),
    ("oc", "oc", "Occitano", "Occitan", "oci_Latn", None, "oc", False, None),
    ("cy", "cy", "Galês", "Cymraeg", "cym_Latn", None, "cy", False, None),
    ("mt", "mt", "Maltês", "Malti", "mlt_Latn", None, "mt", False, None),
    ("lb", "lb", "Luxemburguês", "Lëtzebuergesch", "ltz_Latn", None, "lb", False, None),
    ("af", "af", "Africâner", "Afrikaans", "afr_Latn", None, "af", False, None),
    ("sw", "sw", "Suaíli", "Kiswahili", "swh_Latn", None, "sw", False, None),
    ("id", "id", "Indonésio", "Bahasa Indonesia", "ind_Latn", "id", "id", False, None),
    ("ms", "ms", "Malaio", "Bahasa Melayu", "zsm_Latn", "ms", "ms", False, None),
    ("tl", "tl", "Tagalo (Filipino)", "Tagalog", "tgl_Latn", "tl", "tl", False, None),
    ("jw", "jw", "Javanês", "Basa Jawa", "jav_Latn", None, "jv", False, None),
    ("su", "su", "Sundanês", "Basa Sunda", "sun_Latn", None, "su", False, None),
    ("vi", "vi", "Vietnamita", "Tiếng Việt", "vie_Latn", "vi", "vi", False, None),
    ("th", "th", "Tailandês", "ไทย", "tha_Thai", "th", "th", False, None),
    ("lo", "lo", "Laosiano", "ລາວ", "lao_Laoo", None, "lo", False, None),
    ("km", "km", "Khmer", "ខ្មែរ", "khm_Khmr", None, "km", False, None),
    ("my", "my", "Birmanês", "မြန်မာ", "mya_Mymr", None, "my", False, None),
    ("ta", "ta", "Tâmil", "தமிழ்", "tam_Taml", None, "ta", False, None),
    ("te", "te", "Télugo", "తెలుగు", "tel_Telu", None, "te", False, None),
    ("kn", "kn", "Canarês", "ಕನ್ನಡ", "kan_Knda", None, "kn", False, None),
    ("ml", "ml", "Malaiala", "മലയാളം", "mal_Mlym", None, "ml", False, None),
    ("mr", "mr", "Marati", "मराठी", "mar_Deva", None, "mr", False, None),
    ("gu", "gu", "Guzerate", "ગુજરાતી", "guj_Gujr", None, "gu", False, None),
    ("pa", "pa", "Panjabi", "ਪੰਜਾਬੀ", "pan_Guru", None, "pa", False, None),
    ("ne", "ne", "Nepalês", "नेपाली", "npi_Deva", None, "ne", False, None),
    ("si", "si", "Cingalês", "සිංහල", "sin_Sinh", None, "si", False, None),
    ("as", "as", "Assamês", "অসমীয়া", "asm_Beng", None, "as", False, None),
    ("sa", "sa", "Sânscrito", "संस्कृतम्", "san_Deva", None, "sa", False, None),
    ("ka", "ka", "Georgiano", "ქართული", "kat_Geor", None, "ka", False, None),
    ("hy", "hy", "Armênio", "Հայերեն", "hye_Armn", None, "hy", False, None),
    ("az", "az", "Azerbaijano", "Azərbaycan dili", "azj_Latn", "az", "az", False, None),
    ("kk", "kk", "Cazaque", "Қазақ тілі", "kaz_Cyrl", None, "kk", False, None),
    ("ky", "ky", "Quirguiz", "Кыргызча", "kir_Cyrl", "ky", "ky", False, None),
    ("uz", "uz", "Uzbeque", "Oʻzbek", "uzn_Latn", None, "uz", False, None),
    ("tg", "tg", "Tadjique", "Тоҷикӣ", "tgk_Cyrl", None, "tg", False, None),
    ("tk", "tk", "Turcomeno", "Türkmen", "tuk_Latn", None, "tk", False, None),
    ("mn", "mn", "Mongol", "Монгол", "khk_Cyrl", None, "mn", False, None),
    ("tt", "tt", "Tártaro", "Татар", "tat_Cyrl", None, "tt", False, None),
    ("ba", "ba", "Basquir", "Башҡорт", "bak_Cyrl", None, "ba", False, None),
    ("bo", "bo", "Tibetano", "བོད་སྐད་", "bod_Tibt", None, "bo", False, None),
    ("am", "am", "Amárico", "አማርኛ", "amh_Ethi", None, "am", False, None),
    ("so", "so", "Somali", "Soomaali", "som_Latn", None, "so", False, None),
    ("ha", "ha", "Hauçá", "Hausa", "hau_Latn", None, "ha", False, None),
    ("yo", "yo", "Iorubá", "Yorùbá", "yor_Latn", None, "yo", False, None),
    ("sn", "sn", "Xona", "chiShona", "sna_Latn", None, "sn", False, None),
    ("ln", "ln", "Lingala", "Lingála", "lin_Latn", None, "ln", False, None),
    ("mg", "mg", "Malgaxe", "Malagasy", "plt_Latn", None, "mg", False, None),
    ("ht", "ht", "Crioulo haitiano", "Kreyòl ayisyen", "hat_Latn", None, "ht", False, None),
    ("mi", "mi", "Maori", "Te Reo Māori", "mri_Latn", None, "mi", False, None),
]

IDIOMAS: dict[str, Idioma] = {
    t[0]: Idioma(codigo=t[0], whisper=t[1], nome_pt=t[2], nome_nativo=t[3], nllb=t[4],
                 argos=t[5], bcp47=t[6], rtl=t[7], prompt=t[8])
    for t in _TABELA
}

# Idiomas que o Whisper conhece mas que NÃO estão na tabela (sem NLLB): nomes só para avisos.
_NOMES_EXTRA_WHISPER = {
    "la": "Latim", "br": "Bretão", "fo": "Feroês", "haw": "Havaiano",
}


def obter(codigo: str) -> Idioma | None:
    return IDIOMAS.get(codigo)


def por_codigo_whisper(codigo_whisper: str, preferidos: list[str] | None = None) -> Idioma | None:
    """
    Converte um código devolvido pelo Whisper em um Idioma da tabela.
    Como "zh" pode ser simplificado ou tradicional, se um deles estiver em
    `preferidos` (idiomas da sessão) ele é escolhido.
    """
    preferidos = preferidos or []
    candidatos = [i for i in IDIOMAS.values() if i.whisper == codigo_whisper]
    if not candidatos:
        return None
    for c in candidatos:
        if c.codigo in preferidos:
            return c
    return candidatos[0]


def nome_para_aviso(codigo_whisper: str) -> str:
    """Nome legível de qualquer código do Whisper, mesmo fora da tabela."""
    i = por_codigo_whisper(codigo_whisper)
    if i:
        return i.rotulo
    return _NOMES_EXTRA_WHISPER.get(codigo_whisper, codigo_whisper).upper()


def lista_para_interface() -> list[dict]:
    """Lista ordenada pelo nome em português (sem o português, que é o idioma da casa)."""
    itens = [i for i in IDIOMAS.values() if i.codigo != PORTUGUES]
    itens.sort(key=lambda i: i.nome_pt.lower())
    return [i.para_json() for i in itens]


def validar_lista(codigos: list[str]) -> list[str]:
    """Remove códigos desconhecidos, duplicados e o próprio português."""
    vistos: list[str] = []
    for c in codigos or []:
        if c in IDIOMAS and c != PORTUGUES and c not in vistos:
            vistos.append(c)
    return vistos

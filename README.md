# GMP Tradutor

Tradução de reuniões presenciais em tempo real, **100% no próprio computador**.
Um notebook no centro da mesa ouve a conversa: o que a equipe da GMP fala em
português aparece traduzido para o idioma do visitante, e o que o visitante
fala aparece em português. Nada de áudio ou texto sai da máquina e, depois de
instalado, o sistema funciona com a internet desligada.

## O que você precisa

| Item | Mínimo | Recomendado |
|------|--------|-------------|
| Sistema | Windows 10/11 64 bits (ou Linux) | Windows 11 |
| Memória RAM | 8 GB | 16 GB |
| Espaço em disco | 6 GB livres | 10 GB livres |
| Processador | 4 núcleos (Intel i5 / Ryzen 5 de 2018 ou mais novo) | 8 núcleos ou mais |
| Placa de vídeo | nenhuma (roda na CPU) | NVIDIA com 4 GB ou mais (fica 3 a 4 vezes mais rápido) |
| Navegador | Google Chrome ou Microsoft Edge | — |
| Microfone | o do notebook | microfone de mesa USB (ouve a sala inteira) |

A instalação precisa de internet uma única vez (baixa cerca de 1 GB de modelos sem GPU, ou
3 GB com GPU, que usa modelos maiores e mais precisos).

## Instalar (uma única vez)

1. Copie a pasta do programa para um lugar fixo no computador, de preferência
   **fora do OneDrive** (por exemplo `C:\GMP-Tradutor`). Os modelos ocupam
   mais de 1 GB e não precisam ser sincronizados.
2. Clique duas vezes em **`instalar.bat`** e aguarde. Ele:
   - encontra (ou instala) o Python;
   - cria o ambiente e instala as bibliotecas;
   - detecta se há placa NVIDIA e, se houver, instala o suporte a GPU;
   - baixa os modelos para a pasta `modelos/` e confere a integridade de cada arquivo.
3. No final aparece "Instalação concluída". Se der erro de internet, rode
   `instalar.bat` de novo: o download continua de onde parou.

No Linux: `./instalar.sh` e depois `./iniciar.sh`.

**Levar para outro computador**: copie a pasta inteira (pode incluir `modelos/`, para não baixar
os 1 a 3 GB de novo) e clique em `instalar.bat` lá. O instalador recria o ambiente Python
automaticamente. Se não quiser levar o histórico de reuniões, apague `dados/` e `atas/` antes.

## Usar na reunião

1. Clique duas vezes em **`iniciar.bat`**. Abre uma janela preta (o servidor, deixe
   aberta) e, em seguida, a tela do programa no Chrome/Edge.
2. **Teste o microfone**: fale normalmente e veja se a barra "Microfone" se mexe.
   Se não mexer, escolha outro microfone na lista (o de mesa USB aparece pelo nome).
3. **Escolha o idioma do visitante**: digite para buscar (ex.: "ital", "english",
   "中文") e clique para marcar. Pode marcar mais de um se vierem pessoas de países
   diferentes. A escolha fica salva para a próxima reunião.
4. Clique em **Iniciar reunião**. A tela entra em tela cheia com duas colunas:
   **PORTUGUÊS** à esquerda e o idioma do visitante à direita (com dois idiomas
   de visitante a direita se divide; com três ou mais viram abas, teclas 1 a 9).
5. Vire a tela para os participantes. Ninguém precisa apertar nada: cada frase
   aparece como um balão com o original de um lado e a tradução do outro. A fala
   mais recente fica destacada embaixo; as anteriores sobem como histórico.

Indicadores no topo: **ouvindo…** (alguém está falando), **transcrevendo…/traduzindo…**,
**idioma: …** (idioma detectado) e a barra de nível do microfone. O idioma de cada fala é
escolhido **somente entre os idiomas da sessão**: com português e italiano marcados, toda
fala é tratada como português ou italiano, nunca como um terceiro idioma. (Se quiser que
um idioma de fora seja aceito quando o sistema tiver muita certeza dele, ligue
`"permitir_fora_da_sessao": true` no `config.json`.)

### Sensibilidade do microfone (pessoas longe do notebook)

Na tela inicial, fale da distância em que os participantes vão ficar: a barra deve chegar
perto do meio. Se ficar baixa, aumente o controle **Sensibilidade** (amplificação
automática de até 10×; fica salvo no navegador). Se mesmo em 10× a barra mal se mexe:

1. No Windows, abra Configurações > Sistema > Som > Entrada, escolha o microfone e deixe o
   volume de entrada em 100. Em "Propriedades do dispositivo" alguns notebooks têm
   "Aumento do microfone" (+10 a +20 dB): ative.
2. Use um microfone de mesa USB (omnidirecional) no centro da mesa: é a melhor solução
   para uma sala.
3. Em `config.json`, `vad.limiar_inicio` (padrão 0,4) pode baixar para 0,3 em salas
   silenciosas; e `audio.supressao_ruido` pode ir para `false` se a fala distante estiver
   sendo "engolida" pela supressão de ruído do navegador.

### Atalhos

| Tecla | Ação |
|-------|------|
| **Espaço** | pausar / retomar o microfone |
| **Esc** | sair da tela cheia (**F** volta) |
| **E** | exportar a ata (.docx e .txt) |
| **L** | trocar os idiomas da sessão |
| **N** | nova reunião (limpa a tela; o histórico anterior fica guardado) |
| **+** / **−** | aumentar / diminuir o tamanho do texto |
| **1** a **9** | escolher a aba de idioma (quando há 3 ou mais idiomas) |

### Exportar a ata

Pressione **E** (ou clique em "Exportar"). O programa grava dois arquivos na pasta
`atas/`, com data e hora no nome:

- `ata_AAAA-MM-DD_HH-MM.docx` — tabela com data/hora, idioma, texto original e tradução;
- `ata_AAAA-MM-DD_HH-MM.txt` — a mesma transcrição bilíngue em texto simples.

O navegador também baixa o .docx. O histórico fica guardado em `dados/` mesmo se o
programa for fechado sem exportar; ao abrir de novo, a tela inicial oferece
"Continuar reunião atual".

## Se ficar lento

A meta é a tradução aparecer em menos de 3 segundos depois que a frase termina.
Referência medida com o teste automático (frases de 6 a 8 segundos), já descontado o
silêncio de 0,6 s que fecha a frase:

| Máquina | Modelo | Tempo médio por frase (transcrição + tradução) |
|---------|--------|-----------------------------------------------|
| Notebook com GPU NVIDIA RTX 4060 | large-v3-turbo (beam 5) + NLLB 1.3B | 1,1 s |
| Mesmo notebook só na CPU (i9-13900H, 8 threads) | small + NLLB 600M | 2,75 s |

Com GPU, a tradução também aparece **enquanto a pessoa fala** (texto parcial em itálico,
atualizado a cada 1,5 s) e é consolidada quando a frase termina.

Em um processador mais fraco espere algo entre 3 e 5 segundos com o modelo `small`.
Se estiver demorando mais:

1. Feche outros programas pesados (Teams, navegador com muitas abas, vídeos).
2. Deixe o notebook na tomada e no modo de energia "Desempenho".
3. Abra `config.json` e troque `"modelo": "auto"` por `"modelo": "base"` (mais rápido,
   um pouco menos preciso). Rode `instalar.bat` de novo para baixar esse modelo.
4. Em máquinas fracas o texto parcial (que aparece enquanto a pessoa ainda fala) é
   desligado automaticamente para não atrasar a tradução final. Para desligar sempre,
   use `"parciais": false`.
5. Com placa NVIDIA, confira na tela inicial se aparece "(GPU)" ao lado do modelo. Se
   aparecer "(CPU)", atualize o driver da NVIDIA e rode `instalar.bat` de novo.

## Testar sem reunião

- **Teste automático** (três áudios curtos: português, italiano e inglês):

  ```bat
  .venv\Scripts\python.exe testes\teste_pipeline.py
  ```

  Ele confere se cada idioma é detectado, se a tradução vai para a coluna certa e
  no idioma certo, e mostra o tempo médio por frase.

- **Simular o microfone** com a tela aberta (serve para VPS ou para ver a interface
  funcionando sem falar): inicie a reunião com italiano e inglês e rode

  ```bat
  .venv\Scripts\python.exe testes\simular_microfone.py
  ```

## Rodar em outro computador ou em uma VPS

O áudio é captado pelo navegador e enviado ao servidor, então o servidor pode ficar em
outra máquina (mais forte) e o notebook da sala só abre a página.

1. No servidor, edite `config.json`: `"host": "0.0.0.0"` e defina uma `"senha_acesso"`.
2. Os navegadores só liberam o microfone em páginas seguras (`localhost` ou HTTPS).
   Gere um certificado com `python instalacao/gerar_certificado.py --ip SEU.IP` e ative
   `"https": {"ativo": true}`. Na primeira vez o navegador avisa que o certificado é
   autoassinado: clique em "Avançado" e "Continuar". (Com um domínio próprio, um proxy
   como Caddy ou Nginx com certificado válido também funciona.)
3. Inicie com `./iniciar.sh --sem-navegador` e, no notebook da sala, abra
   `https://SEU.IP:8765/` no Chrome ou Edge.

Observação: nesse caso o áudio trafega pela rede entre o notebook e o seu servidor; use
apenas servidores sob seu controle.

## Privacidade

Reconhecimento de voz (Whisper) e tradução (NLLB-200) rodam localmente com modelos de
código aberto baixados na instalação. O programa não usa nenhuma API, nuvem ou chave de
serviço. `iniciar.bat` liga o modo offline das bibliotecas, então nada é consultado na
internet durante a reunião.

## Configurações (config.json)

| Chave | Padrão | Para que serve |
|-------|--------|----------------|
| `transcricao.modelo` | `auto` | `auto` = large-v3-turbo com GPU, small sem GPU. Outros: tiny, base, small, medium, large-v3 (baixe com `python instalacao/baixar_modelos.py --whisper NOME`) |
| `transcricao.beam_size` | `auto` | `auto` = 5 com GPU (mais preciso), 1 sem GPU (mais rápido) |
| `transcricao.dispositivo` | `auto` | `cpu` ou `cuda` |
| `transcricao.parciais` | `auto` | texto parcial enquanto a pessoa fala (`true`/`false`) |
| `transcricao.traduzir_parciais` | `auto` | tradução já no texto parcial (`auto` = sim com GPU) |
| `transcricao.intervalo_parcial_s` | `1.5` | de quantos em quantos segundos o texto parcial é atualizado |
| `traducao.modelo` | `auto` | `auto` = NLLB 1.3B com GPU (tradução melhor), 600M sem GPU (baixe com `--nllb 1.3B`) |
| `transcricao.permitir_fora_da_sessao` | `false` | `true` aceita um idioma que não está na sessão quando o sistema tem muita certeza dele |
| `audio.ganho_maximo` | `4` | amplificação automática padrão do microfone (1 a 10); o controle "Sensibilidade" da tela sobrepõe |
| `audio.supressao_ruido` | `true` | supressão de ruído do navegador (`false` ajuda com fala distante em sala silenciosa) |
| `vad.limiar_inicio` / `vad.limiar_fim` | `0.4` / `0.3` | sensibilidade do detector de voz; menor = detecta fala mais fraca (e mais ruído) |
| `traducao.motor` | `nllb` | `nllb` (200 idiomas) ou `argos` (mais leve; instale com `instalar.bat argos`) |
| `traducao.beam_size` | `2` | 1 = mais rápido, 3 ou 4 = um pouco melhor |
| `vad.silencio_fim_ms` | `700` | silêncio (ms) que encerra uma frase; menor = mais rápido, maior = frases mais inteiras |
| `vad.corte_suave_apos_s` | `10` | em falas longas, fecha um bloco na primeira pausa curta após este tempo (a tradução vai saindo em partes) |
| `servidor.senha_acesso` | vazio | senha pedida na tela inicial (use em VPS) |
| `servidor.abrir_navegador` | `true` | abrir o Chrome/Edge automaticamente |

## Pastas

- `modelos/` — modelos baixados (com `manifesto.json` de verificação)
- `atas/` — atas exportadas
- `dados/` — histórico da reunião atual e perfil do navegador
- `servidor/` — código do servidor (Python) · `web/index.html` — a tela · `web/logo.png` — logo da GMP (troque o arquivo para atualizar o logo na tela e na ata)
- `testes/` — teste automático, simulador de microfone e áudios de exemplo

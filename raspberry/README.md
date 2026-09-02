# CrySense AI

> Babá eletrônica inteligente com análise local de choro, monitoramento ambiental, vídeo em tempo real e detecção visual de situações de risco no berço.

## Visão geral

O **CrySense AI** foi desenvolvido para oferecer mais tranquilidade e segurança aos cuidadores, especialmente a pais de primeira viagem. Diferentemente de uma babá eletrônica convencional, que apenas transmite áudio e vídeo, o sistema utiliza inteligência artificial para identificar o choro do bebê e classificar seu padrão como mais associado à **fome** ou à **cólica**.

O áudio capturado é padronizado em 16 kHz e convertido em descritores temporais e espectrais, como energia, cruzamento por zero, centroide, largura de banda e fluxo espectral. Os modelos comparam esse conjunto de características com os exemplos utilizados no treinamento. A análise acontece em duas etapas: primeiro o sistema diferencia `choro` de `ruído`; depois, quando o choro é confirmado, classifica-o como `fome` ou `cólica`.

O monitoramento também reúne vídeo ao vivo, condições ambientais e visão computacional. O Raspberry Pi transmite as imagens localmente, enquanto um computador pode executar **OpenCV + YOLO** para localizar pessoas por meio de *bounding boxes* e verificar a entrada em uma zona de risco desenhada pelo próprio usuário sobre o berço. Os resultados, alertas e ocorrências são apresentados no painel web, na tela TFT e no aplicativo Android.

Em situações associadas à cólica, o protótipo pode acionar uma intervenção sonora configurável, como ruído branco ou rosa, para auxiliar no conforto do bebê. O histórico de eventos também permite acompanhar a recorrência dos padrões identificados. O CrySense AI é uma ferramenta de apoio: não diagnostica cólica crônica, não substitui avaliação médica e não dispensa a supervisão de um responsável.

## Problema que o projeto busca solucionar

O choro é um dos principais meios de comunicação do bebê, mas sua interpretação pode gerar dúvida e ansiedade, sobretudo para cuidadores sem experiência. O CrySense AI busca reduzir essa incerteza ao reunir, em uma única solução, análise do choro, vídeo, dados ambientais, alertas de risco e histórico de ocorrências, mantendo o processamento principal na rede local para diminuir latência e preservar a privacidade.

## Principais funcionalidades

- Monitoramento contínuo do áudio e do ambiente.
- Detecção de `choro` × `ruído` por uma primeira IA.
- Classificação do choro como `fome` × `cólica` por uma segunda IA.
- Padronização do áudio e extração local de características temporais e espectrais.
- Análise manual de arquivos WAV para demonstrações em locais barulhentos.
- Vídeo ao vivo no painel web e no aplicativo Android.
- Detecção de pessoas com YOLO e exibição de *bounding boxes*.
- Zona visual de risco desenhada pelo usuário sobre o vídeo.
- Alertas locais no aplicativo, painel web e tela TFT.
- Painel TFT atualizado em tempo real com Wi-Fi, IP, microfone, câmera e dados ambientais.
- Monitoramento de temperatura, umidade e pressão atmosférica.
- Registro local do histórico de ocorrências em SQLite.
- Intervenção sonora configurável em eventos associados à cólica.
- Ponto de acesso Wi-Fi de emergência para uso fora da rede habitual.

## Tecnologias e metodologias

- **Computação embarcada:** Raspberry Pi 3B com Raspberry Pi OS Lite.
- **Backend local:** Python, FastAPI, API REST e SQLite.
- **Aprendizado de máquina:** scikit-learn, Random Forest e modelos serializados com Joblib.
- **Processamento de áudio:** NumPy, reamostragem, análise temporal e espectral.
- **Visão computacional:** OpenCV e Ultralytics YOLO executados no computador.
- **Aplicativo móvel:** Kotlin e Jetpack Compose para Android.
- **Transmissão:** vídeo MJPEG e comunicação HTTP pela rede Wi-Fi local.
- **Sensoriamento:** BME280, microfone digital INMP441, amplificador MAX98357A e tela TFT ST7735.
- **Pipeline em duas etapas no tempo real:** a IA de classificação do tipo só é executada após a confirmação do choro captado pelo microfone.
- **Confirmação temporal da escuta ativa:** limiares de confiança e múltiplas janelas consecutivas reduzem ativações isoladas.
- **Arquitetura local-first:** áudio, eventos e dados sensíveis permanecem sob controle da rede local.

## Arquitetura técnica

1. **IA 1 — trigger:** `cry` × `noise`, Random Forest sobre uma janela de áudio de 1 segundo.
2. **IA 2 — tipo:** `colic` × `hunger`, Random Forest sobre um clip de 6 segundos. Na escuta ativa, ela roda após a IA 1 confirmar choro em 3 de 5 janelas; no upload, recebe diretamente o arquivo que o usuário já informou conter choro.
3. **Aplicação:** FastAPI local, SQLite, BME280, TFT ST7735 e webcam USB. O dashboard móvel é servido na própria rede Wi-Fi.
4. **Visão opcional no computador:** o Raspberry só entrega o MJPEG. Um processo Python no computador executa OpenCV + YOLO, confirma padrões de risco e devolve o alerta pela rede local.

O vídeo é transmitido localmente por MJPEG. O Raspberry não executa a visão computacional, portanto áudio, sensores e transmissão permanecem leves mesmo quando a análise visual está ativa no computador.

Se a webcam estiver montada em outra orientação, ajuste `CRYSENSE_CAMERA_ROTATION` em `/etc/crysense.env` e reinicie o serviço. O valor é em graus no sentido horário: `90`, `180` ou `270`; para girar 90° para a esquerda use `270`. Valores como `265` permitem corrigir uma pequena inclinação física.

## Painel local da TFT

A tela ST7735 usa a orientação horizontal de 160×128 pixels e funciona independentemente do painel web. Ela é atualizada em segundo plano mesmo quando nenhum celular está conectado e apresenta:

- situação do Wi-Fi, nome da rede e endereço IP;
- temperatura, umidade e pressão lidas pelo BME280;
- estado do microfone e barra dinâmica do nível de áudio;
- fase atual das IAs e estado da câmera;
- tela prioritária por 15 segundos para alertas de fome, cólica ou risco visual.

Quando o ponto de acesso de emergência estiver ativo, a TFT mostra **REDE CRYSENSE** e o IP `10.42.0.1`, facilitando a conexão durante apresentações e feiras.

## Pinagem definida

| Barramento | Componente | GPIO BCM | Pino físico |
|---|---|---:|---:|
| I2C | BME280 SDA/SCL | 2 / 3 | 3 / 5 |
| SPI | TFT MOSI/SCLK/CS | 10 / 11 / 8 | 19 / 23 / 24 |
| SPI | TFT RST/DC/LED | 24 / 25 / 23 | 18 / 22 / 16 |
| I2S | BCLK/LRCLK | 18 / 19 | 12 / 35 |
| I2S | INMP441 SD | 20 | 38 |
| I2S | MAX98357A DIN | 21 | 40 |
| Reservado pelo overlay | detecção interna do ADC | 22 | 15 |

TFT, BME280 e INMP441 usam 3,3 V. MAX98357A usa 5 V. Todos os GNDs devem ser comuns. O GPIO22/pino físico 15 **deve permanecer sem conexão**: o overlay o usa somente com pull-up interno para habilitar a captura do INMP441.

## Desenvolvimento no PC

```powershell
cd crysense
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn crysense.app:app --reload --port 8080
```

Abra `http://127.0.0.1:8080`. Por padrão, webcam, áudio, BME280 e TFT ficam desabilitados no PC.

## Demonstração em feira: análise de áudio enviado

O dashboard possui a seção **Analisar áudio para demonstração**. Se o ruído da feira tornar o microfone inadequado, envie um arquivo **WAV PCM** de até 12 MB que você já sabe conter choro, preferencialmente com cerca de seis segundos. O upload não executa a IA 1: o arquivo segue diretamente para a IA 2, que classifica `cólica` × `fome`.

Se a IA 2 atingir os limiares de confiança e margem, a decisão passa pelo mesmo fluxo de alerta do microfone: cria ocorrência, atualiza o app, mostra a mensagem na TFT e executa a ação configurada para cada tipo. A IA 1 permanece exclusiva da escuta ativa em tempo real.

## Visão no computador (OpenCV + YOLO)

O serviço visual deve executar no computador conectado à mesma rede Wi-Fi do Raspberry. Ele consome `http://IP_DO_RASPBERRY:8080/api/camera/stream`, roda o modelo YOLO no PC e envia apenas o resultado para o Raspberry. O dashboard passa a mostrar o estado **Visão no computador** e, em caso de risco confirmado, o Raspberry registra a ocorrência e mostra um alerta na TFT.

Primeiro, envie esta versão ao Raspberry e, se desejar autenticar a comunicação, defina a mesma senha nos dois lados:

```ini
# /etc/crysense.env, no Raspberry
CRYSENSE_VISION_TOKEN=uma-senha-local-longa
```

No computador, instale as dependências extras uma única vez. Para a demonstração sem treinamento, o comando abaixo usa o YOLO genérico leve `yolo11n.pt`: ele é baixado no **computador** na primeira execução, portanto deixe o PC conectado à internet nesse momento. O Raspberry nunca baixa nem executa o modelo.

```powershell
cd crysense
.\.venv\Scripts\Activate.ps1
pip install -e ".[vision]"
```

Para iniciar a demonstração sem nenhuma área marcada ainda:

```powershell
.\deploy\run_vision_from_windows.ps1
```

O alerta somente é emitido depois de três inferências consecutivas. O YOLO genérico pode detectar `person`, mas não entende por si só a ação de tentar sair do berço: nesta demonstração ele alerta quando a pessoa detectada ocupa a zona de saída configurada. No painel web ou no aplicativo, desenhe e salve a zona diretamente sobre o vídeo; ela é armazenada no Raspberry e aplicada pelo computador sem reiniciar o monitor. Também é possível informar a zona no comando:

```powershell
.\deploy\run_vision_from_windows.ps1 -RiskZone "0.15,0.00,0.85,0.25"
```

Os quatro valores da zona são `x1,y1,x2,y2`, normalizados entre 0 e 1, e devem cobrir a região acima/externa da grade do berço. A precisão real para “tentativa de sair” exige um dataset filmado no mesmo ângulo, com exemplos de posições normais e de risco. A visão é um apoio ao responsável, não um recurso de segurança autônomo.

Quando houver um modelo treinado, informe o arquivo `.pt` e as classes que ele reconhece:

```powershell
.\deploy\run_vision_from_windows.ps1 -Model "C:\Modelos\baby_safety.pt" -RiskLabels "climb,escape_risk" -RiskZone ""
```

## Treino

Os datasets devem conter apenas pastas de classe e WAVs, como já está organizado neste projeto.

```powershell
crysense-train trigger --dataset .\datasetIA1 --output .\models
crysense-train type --dataset .\datasetIA2 --output .\models
```

Isso produz `models/trigger.joblib` e `models/type.joblib`. Random Forest não usa épocas. As métricas geradas são baseline; a avaliação final precisa separar gravações-origem, não somente arquivos consecutivos.

## Envio e instalação no Raspberry

No PC, com o Raspberry acessível pelo atalho SSH `crysense`, execute uma única vez por release:

```powershell
cd crysense
.\deploy\deploy_from_windows.ps1
```

O script copia somente `src`, `deploy`, `models` e os arquivos de configuração; **não** envia datasets, banco de dados, modelos visuais ou a `.venv` do Windows. No Pi ele cria a `.venv` ARM64 correta, instala o serviço `crysense` e o inicia. O dashboard ficará em `http://IP_DO_RASPBERRY:8080`.

Para acompanhar ou reiniciar o serviço:

```bash
ssh crysense
sudo systemctl status crysense
sudo journalctl -u crysense -f
sudo systemctl restart crysense
```

## Wi-Fi para feira: ponto de acesso de emergência

O Raspberry pode criar a rede Wi-Fi `CrySense-Setup` quando não encontrar nenhuma rede conhecida. Assim, notebook e celular podem se conectar diretamente ao dispositivo, sem depender do Wi-Fi da feira. Quando essa rede estiver ativa, o painel estará em `http://10.42.0.1:8080`.

Configure uma única vez, escolhendo uma senha WPA2 própria:

```bash
sudo /opt/crysense/deploy/configure_fallback_ap.sh CrySense-Setup 'SUA_SENHA_FORTE'
```

O perfil da rede normal tem prioridade maior. Portanto, o ponto de acesso não deve ser ativado quando o Raspberry conseguir entrar em um Wi-Fi conhecido. Para a maior previsibilidade em feiras, ainda é recomendado levar um hotspot ou roteador portátil próprio.

## Ativação por etapas no Raspberry

1. Conecte inicialmente apenas a webcam e confirme `v4l2-ctl --list-devices`.
2. No celular na mesma rede Wi-Fi, abra o dashboard e confirme o vídeo.
3. Ative I2C e SPI com `sudo raspi-config`; reinicie e use `i2cdetect -y 1` para encontrar o BME280.
4. Teste o TFT e o BME280 mantendo `CRYSENSE_ENABLE_AUDIO=false` em `/etc/crysense.env`.
5. O instalador compila `deploy/crysense-i2s-full-duplex-overlay.dts`, instala o overlay e configura os dispositivos de áudio. Na primeira instalação ele solicitará uma reinicialização para carregar o I2S full-duplex.

### INMP441 + MAX98357A: I2S full-duplex validado

Os dois módulos compartilham os clocks BCLK/LRCLK, por isso devem aparecer como uma única placa ALSA:

```ini
# /boot/firmware/config.txt
dtoverlay=crysense-i2s-full-duplex
```

Depois de reiniciar, ela aparece como `snd_rpi_hifiberry_dac8x`, com dois canais de entrada e dois de saída. A configuração usada pelo serviço é:

```ini
# /etc/crysense.env
CRYSENSE_ENABLE_AUDIO=true
CRYSENSE_AUDIO_INPUT_DEVICE=snd_rpi_hifiberry_dac8x
CRYSENSE_AUDIO_OUTPUT_DEVICE=snd_rpi_hifiberry_dac8x
CRYSENSE_AUDIO_INPUT_CHANNELS=2
CRYSENSE_AUDIO_INPUT_CHANNEL=0
CRYSENSE_AUDIO_OUTPUT_CHANNELS=2
CRYSENSE_PINK_NOISE_VOLUME=0.10
```

O INMP441 está ligado ao canal esquerdo pelo pino L/R aterrado; por isso a aplicação seleciona o canal `0`. O pipeline recebe a taxa nativa do hardware e reamostra internamente para 16 kHz antes de executar os dois modelos. Não carregue também `dtoverlay=i2s-dac`: o Pi 3B possui apenas uma controladora I2S e o overlay full-duplex já atende entrada e saída.

O volume do ruído rosa fica limitado por software a um intervalo de `0` a `1`; o padrão `0.10` reduz o pico de consumo do MAX98357A. Ainda assim, use fonte e cabo capazes de alimentar Raspberry, webcam, TFT e amplificador. `vcgencmd get_throttled` deve retornar `0x0`; bits persistentes de subtensão indicam que a alimentação precisa ser corrigida.

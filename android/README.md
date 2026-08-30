# CrySense AI para Android

Aplicativo de monitoramento local do CrySense AI, desenvolvido em Kotlin com Jetpack Compose. O app consome a API do Raspberry Pi pela rede Wi-Fi, exibe a câmera MJPEG em tempo real, dados ambientais, estado da escuta, ocorrências, classificação de arquivos de áudio e resultados do servidor de visão.

## Requisitos

- Android Studio com JDK 11 ou superior.
- Android SDK 35.
- Celular e Raspberry Pi na mesma rede Wi-Fi.
- Servidor CrySense em execução no Raspberry Pi.

## Executar

1. Abra esta pasta `android` no Android Studio.
2. Aguarde a sincronização do Gradle.
3. Selecione um dispositivo Android e execute o módulo `app`.
4. Nas configurações do aplicativo, informe o endereço do Raspberry Pi, por exemplo `http://192.168.1.100:8000`.

Pelo terminal do Windows:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug
```

O painel atual não depende da nuvem. O módulo preserva uma integração Firebase legada, ativada automaticamente apenas quando existir um `app/google-services.json` válido. Esse arquivo, `local.properties`, APKs, caches, builds e chaves de assinatura são locais e não devem ser versionados.

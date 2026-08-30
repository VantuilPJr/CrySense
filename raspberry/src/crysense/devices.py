"""Mostra os dispositivos de áudio reconhecidos por PortAudio/ALSA."""

import sounddevice as sd


def main() -> None:
    default_input, default_output = sd.default.device
    print("Dispositivos de áudio disponíveis:\n")
    for index, device in enumerate(sd.query_devices()):
        directions: list[str] = []
        if device["max_input_channels"]:
            directions.append(f"entrada={device['max_input_channels']}")
        if device["max_output_channels"]:
            directions.append(f"saída={device['max_output_channels']}")
        if not directions:
            continue
        default = []
        if index == default_input:
            default.append("entrada padrão")
        if index == default_output:
            default.append("saída padrão")
        suffix = f" — {', '.join(default)}" if default else ""
        print(f"[{index}] {device['name']} ({', '.join(directions)}){suffix}")


if __name__ == "__main__":
    main()

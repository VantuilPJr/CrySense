package com.vantuilpjunior.crysenseai.ui.dashboard

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.Image
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeviceThermostat
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vantuilpjunior.crysenseai.data.remote.local.CryEventDto
import com.vantuilpjunior.crysenseai.data.remote.local.AudioAnalysisDto
import com.vantuilpjunior.crysenseai.data.remote.local.RaspberryMonitorState
import com.vantuilpjunior.crysenseai.data.remote.local.VisionDetectionDto
import com.vantuilpjunior.crysenseai.data.remote.local.normalizeEndpoint
import com.vantuilpjunior.crysenseai.ui.theme.BackgroundLight
import com.vantuilpjunior.crysenseai.ui.theme.PastelBlueDark
import com.vantuilpjunior.crysenseai.ui.theme.PastelBlueMain
import com.vantuilpjunior.crysenseai.ui.theme.SoftText
import com.vantuilpjunior.crysenseai.ui.theme.SurfaceWhite
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

private val HealthyGreen = Color(0xFF059669)
private val WarningAmber = Color(0xFFD97706)
private val AlertRed = Color(0xFFDC2626)

@Composable
fun LocalDashboardScreen(
    state: RaspberryMonitorState,
    endpoint: String,
    onEndpointChange: (String) -> Unit,
    audioUploadInProgress: Boolean,
    audioUploadResult: AudioAnalysisDto?,
    audioUploadError: String?,
    onSelectAudio: () -> Unit,
    visionZone: List<Double>?,
    visionZoneSaving: Boolean,
    visionZoneMessage: String?,
    onSaveVisionZone: (List<Double>) -> Unit,
    onClearVisionZone: () -> Unit,
) {
    var showSettings by remember { mutableStateOf(false) }
    var markingVisionZone by remember { mutableStateOf(false) }
    var draftVisionZone by remember(visionZone) { mutableStateOf(visionZone) }
    val status = state.status

    Surface(modifier = Modifier.fillMaxSize(), color = BackgroundLight) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Header(online = state.online, onSettingsClick = { showSettings = true })
            CameraCard(
                state = state,
                visionZone = draftVisionZone,
                detections = status.vision.detections,
                markingVisionZone = markingVisionZone,
                onZoneChange = { draftVisionZone = it },
                onZoneMarked = { markingVisionZone = false },
            )
            VisionZoneCard(
                zone = draftVisionZone,
                isMarking = markingVisionZone,
                isSaving = visionZoneSaving,
                message = visionZoneMessage,
                vision = status.vision,
                onStartMarking = { markingVisionZone = true },
                onSave = { draftVisionZone?.let(onSaveVisionZone) },
                onClear = onClearVisionZone,
            )
            MonitoringCard(state = state)
            AudioUploadCard(
                isAnalyzing = audioUploadInProgress,
                result = audioUploadResult,
                error = audioUploadError,
                onSelectAudio = onSelectAudio,
            )

            Text("Ambiente", style = MaterialTheme.typography.labelLarge, color = SoftText)
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                SensorCard(
                    "Temperatura",
                    status.sensor.temperature?.let { "%.1f °C".format(it) } ?: "-- °C",
                    Icons.Default.DeviceThermostat,
                    Modifier.weight(1f),
                )
                SensorCard(
                    "Umidade",
                    status.sensor.humidity?.let { "%.0f %%".format(it) } ?: "-- %",
                    Icons.Default.WaterDrop,
                    Modifier.weight(1f),
                )
                SensorCard(
                    "Pressão",
                    status.sensor.pressure?.let { "%.0f hPa".format(it) } ?: "-- hPa",
                    Icons.Default.DeviceThermostat,
                    Modifier.weight(1f),
                )
            }

            EventsCard(events = state.events)
            if (state.error != null) {
                Text(state.error, color = AlertRed, style = MaterialTheme.typography.bodySmall)
            }
            Text(
                "Monitoramento local. O CrySense é uma ferramenta de apoio e não substitui o cuidado de um responsável.",
                color = SoftText,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp),
            )
        }
    }

    if (showSettings) {
        EndpointDialog(
            currentEndpoint = endpoint,
            onDismiss = { showSettings = false },
            onSave = {
                onEndpointChange(it)
                showSettings = false
            },
        )
    }
}

@Composable
private fun AudioUploadCard(
    isAnalyzing: Boolean,
    result: AudioAnalysisDto?,
    error: String?,
    onSelectAudio: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Analisar áudio", color = PastelBlueDark, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(
                "Para a demonstração em ambiente barulhento, envie um WAV PCM. Uma confirmação de cólica ou fome gera o mesmo alerta do monitoramento ao vivo.",
                color = SoftText,
                style = MaterialTheme.typography.bodySmall,
            )
            Button(onClick = onSelectAudio, enabled = !isAnalyzing) {
                Text(if (isAnalyzing) "Analisando…" else "Selecionar WAV")
            }
            when {
                error != null -> Text(error, color = AlertRed, style = MaterialTheme.typography.bodySmall)
                result != null -> {
                    val confirmation = result.triggerConfirmation
                    val trigger = if (confirmation.confirmed) {
                        "IA 1: choro confirmado (${confirmation.positiveWindows}/${confirmation.windowSize}; pico ${(result.trigger.confidence * 100).toInt()}%)"
                    } else {
                        "IA 1: não confirmou (${confirmation.positiveWindows}/${confirmation.requiredWindows}; pico ${(result.trigger.confidence * 100).toInt()}%)"
                    }
                    val type = result.classification?.let { " · IA 2: ${labelFor(it.label)} ${(it.confidence * 100).toInt()}%" }.orEmpty()
                    Text(trigger + type, color = if (result.alertTriggered) HealthyGreen else WarningAmber, fontWeight = FontWeight.SemiBold)
                    Text(result.message, color = SoftText, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun Header(online: Boolean, onSettingsClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column {
            Text("CrySense", color = PastelBlueDark, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text("Monitoramento local", color = SoftText, style = MaterialTheme.typography.bodySmall)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            StatusPill(online)
            IconButton(onClick = onSettingsClick) {
                Icon(Icons.Default.Settings, contentDescription = "Configurar Raspberry", tint = PastelBlueDark)
            }
        }
    }
}

@Composable
private fun StatusPill(online: Boolean) {
    val color = if (online) HealthyGreen else AlertRed
    Surface(shape = RoundedCornerShape(99.dp), color = color.copy(alpha = 0.12f)) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Surface(modifier = Modifier.size(8.dp), shape = RoundedCornerShape(99.dp), color = color) {}
            Text(
                if (online) "Conectado" else "Sem conexão",
                color = color,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun CameraCard(
    state: RaspberryMonitorState,
    visionZone: List<Double>?,
    detections: List<VisionDetectionDto>,
    markingVisionZone: Boolean,
    onZoneChange: (List<Double>) -> Unit,
    onZoneMarked: () -> Unit,
) {
    val camera = state.status.camera
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Default.Videocam, contentDescription = null, tint = PastelBlueDark)
                Text("Câmera ao vivo", color = PastelBlueDark, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.weight(1f))
                Text(
                    if (camera.running) "AO VIVO" else "INDISPONÍVEL",
                    color = if (camera.running) HealthyGreen else WarningAmber,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                )
            }
            if (camera.running) {
                MjpegCamera(
                    endpoint = state.endpoint,
                    visionZone = visionZone,
                    detections = detections,
                    markingVisionZone = markingVisionZone,
                    onZoneChange = onZoneChange,
                    onZoneMarked = onZoneMarked,
                )
            } else {
                Surface(
                    modifier = Modifier.fillMaxWidth().height(220.dp),
                    shape = RoundedCornerShape(14.dp),
                    color = PastelBlueMain.copy(alpha = 0.25f),
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                        Icon(Icons.Default.Videocam, contentDescription = null, tint = PastelBlueDark, modifier = Modifier.size(38.dp))
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(camera.error ?: "Aguardando a webcam do Raspberry", color = SoftText, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = 18.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun MjpegCamera(
    endpoint: String,
    visionZone: List<Double>?,
    detections: List<VisionDetectionDto>,
    markingVisionZone: Boolean,
    onZoneChange: (List<Double>) -> Unit,
    onZoneMarked: () -> Unit,
) {
    val streamUrl = "${endpoint.trimEnd('/')}/api/camera/stream?mobile=1"
    var frame by remember(streamUrl) { mutableStateOf<Bitmap?>(null) }
    var error by remember(streamUrl) { mutableStateOf<String?>(null) }

    LaunchedEffect(streamUrl) {
        withContext(Dispatchers.IO) {
            while (currentCoroutineContext().isActive) {
                var connection: HttpURLConnection? = null
                try {
                    connection = (URL(streamUrl).openConnection() as HttpURLConnection).apply {
                        connectTimeout = 6_000
                        readTimeout = 0
                        useCaches = false
                        setRequestProperty("Accept", "multipart/x-mixed-replace")
                    }
                    if (connection.responseCode !in 200..299) {
                        throw IOException("A câmera respondeu com código ${connection.responseCode}.")
                    }
                    connection.inputStream.buffered().use { stream ->
                        readMjpegFrames(stream) { bitmap ->
                            withContext(Dispatchers.Main.immediate) {
                                frame = bitmap
                                error = null
                            }
                        }
                    }
                    throw IOException("A transmissão da câmera foi encerrada.")
                } catch (exception: Exception) {
                    if (exception is CancellationException) throw exception
                    withContext(Dispatchers.Main.immediate) {
                        if (frame == null) {
                            error = "Não foi possível receber o vídeo. Tentando reconectar..."
                        }
                    }
                    delay(1_500)
                } finally {
                    connection?.disconnect()
                }
            }
        }
    }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(240.dp)
            .clip(RoundedCornerShape(14.dp)),
        color = PastelBlueMain.copy(alpha = 0.25f),
    ) {
        val currentFrame = frame
        if (currentFrame != null) {
            Box(modifier = Modifier.fillMaxSize()) {
                Image(
                    bitmap = currentFrame.asImageBitmap(),
                    contentDescription = "Vídeo ao vivo da câmera",
                    contentScale = ContentScale.FillBounds,
                    modifier = Modifier.fillMaxSize(),
                )
                RiskZoneOverlay(
                    zone = visionZone,
                    detections = detections,
                    enabled = markingVisionZone,
                    onZoneChange = onZoneChange,
                    onZoneMarked = onZoneMarked,
                    modifier = Modifier.fillMaxSize(),
                )
            }
        } else {
            Column(
                modifier = Modifier.fillMaxSize().padding(18.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(Icons.Default.Videocam, contentDescription = null, tint = PastelBlueDark, modifier = Modifier.size(38.dp))
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    error ?: "Conectando ao vídeo ao vivo...",
                    color = SoftText,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun VisionZoneCard(
    zone: List<Double>?,
    isMarking: Boolean,
    isSaving: Boolean,
    message: String?,
    vision: com.vantuilpjunior.crysenseai.data.remote.local.VisionDto,
    onStartMarking: () -> Unit,
    onSave: () -> Unit,
    onClear: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("Zona visual de risco", color = PastelBlueDark, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Text(
                "Marque no vídeo a região acima ou do lado externo da grade. A demonstração alerta quando uma pessoa aparece nessa área.",
                color = SoftText,
                style = MaterialTheme.typography.bodySmall,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onStartMarking, enabled = !isSaving) {
                    Text(if (isMarking) "Arraste no vídeo" else "Marcar no vídeo")
                }
                Button(onClick = onSave, enabled = zone != null && !isMarking && !isSaving) {
                    Text(if (isSaving) "Salvando…" else "Salvar marcação")
                }
            }
            TextButton(onClick = onClear, enabled = zone != null && !isSaving) { Text("Remover marcação") }
            if (isMarking) {
                Text("Agora arraste o dedo sobre a área de risco no vídeo acima.", color = WarningAmber, style = MaterialTheme.typography.bodySmall)
            } else if (message != null) {
                val isSuccess = message.startsWith("Marcação salva") || message.startsWith("Marcação removida")
                Text(message, color = if (isSuccess) HealthyGreen else AlertRed, style = MaterialTheme.typography.bodySmall)
            } else if (zone != null) {
                Text("Área atual: ${zone.joinToString { "${(it * 100).toInt()}%" }}", color = SoftText, style = MaterialTheme.typography.bodySmall)
            } else {
                Text("Nenhuma área marcada. A visão não gerará alerta até você desenhar uma região.", color = SoftText, style = MaterialTheme.typography.bodySmall)
            }
            if (vision.connected) {
                val visualText = if (vision.alert) "Alerta visual: ${vision.detail ?: "verifique o berço"}" else "Visão no PC: ${vision.detail ?: "monitorando"}"
                Text(visualText, color = if (vision.alert) AlertRed else HealthyGreen, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun RiskZoneOverlay(
    zone: List<Double>?,
    detections: List<VisionDetectionDto>,
    enabled: Boolean,
    onZoneChange: (List<Double>) -> Unit,
    onZoneMarked: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var startPoint by remember { mutableStateOf<Offset?>(null) }
    val safeZone = zone?.takeIf { it.size == 4 }

    Canvas(
        modifier = modifier.pointerInput(enabled) {
            if (enabled) {
                detectDragGestures(
                    onDragStart = { start ->
                        startPoint = start
                        onZoneChange(zoneFromPoints(start, start, size.width, size.height))
                    },
                    onDrag = { change, _ ->
                        startPoint?.let { start ->
                            onZoneChange(zoneFromPoints(start, change.position, size.width, size.height))
                        }
                    },
                    onDragEnd = {
                        startPoint = null
                        onZoneMarked()
                    },
                    onDragCancel = { startPoint = null },
                )
            }
        },
    ) {
        if (safeZone != null) {
            val left = (safeZone[0] * size.width).toFloat()
            val top = (safeZone[1] * size.height).toFloat()
            val width = ((safeZone[2] - safeZone[0]) * size.width).toFloat()
            val height = ((safeZone[3] - safeZone[1]) * size.height).toFloat()
            drawRect(color = WarningAmber.copy(alpha = 0.22f), topLeft = Offset(left, top), size = Size(width, height))
            drawRect(color = WarningAmber, topLeft = Offset(left, top), size = Size(width, height), style = Stroke(width = 3f))
        }
        detections.forEach { detection ->
            if (detection.box.size != 4) return@forEach
            val left = (detection.box[0] * size.width).toFloat()
            val top = (detection.box[1] * size.height).toFloat()
            val width = ((detection.box[2] - detection.box[0]) * size.width).toFloat()
            val height = ((detection.box[3] - detection.box[1]) * size.height).toFloat()
            drawRect(color = PastelBlueDark, topLeft = Offset(left, top), size = Size(width, height), style = Stroke(width = 3f))
            val label = "${detection.label} ${(detection.confidence * 100).toInt()}%"
            val textPaint = Paint().apply {
                color = android.graphics.Color.WHITE
                textSize = 28f
                typeface = android.graphics.Typeface.DEFAULT_BOLD
            }
            val labelTop = (top - 30f).coerceAtLeast(0f)
            drawRect(color = PastelBlueDark, topLeft = Offset(left, labelTop), size = Size(textPaint.measureText(label) + 12f, 30f))
            drawContext.canvas.nativeCanvas.drawText(
                label,
                left + 6f,
                labelTop + 23f,
                textPaint,
            )
        }
    }
}

private fun zoneFromPoints(first: Offset, second: Offset, width: Int, height: Int): List<Double> {
    val firstX = (first.x / width).coerceIn(0f, 1f).toDouble()
    val firstY = (first.y / height).coerceIn(0f, 1f).toDouble()
    val secondX = (second.x / width).coerceIn(0f, 1f).toDouble()
    val secondY = (second.y / height).coerceIn(0f, 1f).toDouble()
    return listOf(minOf(firstX, secondX), minOf(firstY, secondY), maxOf(firstX, secondX), maxOf(firstY, secondY))
}

/** Lê quadros JPEG de uma resposta multipart MJPEG sem depender de WebView. */
private suspend fun readMjpegFrames(stream: InputStream, onFrame: suspend (Bitmap) -> Unit) {
    val jpeg = ByteArrayOutputStream()
    var previousByte = -1
    var collectingJpeg = false
    var lastDecodedAt = 0L

    while (currentCoroutineContext().isActive) {
        val currentByte = stream.read()
        if (currentByte == -1) return

        if (!collectingJpeg) {
            if (previousByte == JPEG_MARKER && currentByte == JPEG_START) {
                jpeg.reset()
                jpeg.write(JPEG_MARKER)
                jpeg.write(JPEG_START)
                collectingJpeg = true
            }
        } else {
            jpeg.write(currentByte)
            when {
                jpeg.size() > MAX_JPEG_FRAME_BYTES -> {
                    jpeg.reset()
                    collectingJpeg = false
                }
                previousByte == JPEG_MARKER && currentByte == JPEG_END -> {
                    val now = System.currentTimeMillis()
                    if (now - lastDecodedAt >= 100L) {
                        val bitmap = BitmapFactory.decodeByteArray(jpeg.toByteArray(), 0, jpeg.size())
                        if (bitmap != null) {
                            onFrame(bitmap)
                            lastDecodedAt = now
                        }
                    }
                    jpeg.reset()
                    collectingJpeg = false
                }
            }
        }
        previousByte = currentByte
    }
}

private const val JPEG_MARKER = 0xFF
private const val JPEG_START = 0xD8
private const val JPEG_END = 0xD9
private const val MAX_JPEG_FRAME_BYTES = 2 * 1024 * 1024

@Composable
private fun MonitoringCard(state: RaspberryMonitorState) {
    val pipeline = state.status.pipeline
    val audio = state.status.audio
    val mainLabel = when (pipeline.phase) {
        "capturing_type_audio" -> "Analisando o choro"
        "monitoring" -> "Monitorando"
        "error" -> "Atenção necessária"
        else -> "Aguardando áudio"
    }
    val latest = pipeline.lastType ?: pipeline.lastTrigger
    val description = latest?.let { "${labelFor(it.label)} · ${(it.confidence * 100).toInt()}%" }
        ?: if (audio.listening) "Microfone ouvindo" else "Microfone indisponível"
    val level = ((audio.levelRms ?: 0.0) * 8).coerceIn(0.0, 1.0).toFloat()

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Icon(Icons.Default.Mic, contentDescription = null, tint = if (audio.listening) HealthyGreen else WarningAmber, modifier = Modifier.size(34.dp))
            Text(mainLabel, color = PastelBlueDark, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text(description, color = SoftText, style = MaterialTheme.typography.bodyMedium)
            Text(if (audio.listening) "Ouvindo agora" else (audio.error ?: "Verificando áudio"), color = if (audio.listening) HealthyGreen else WarningAmber, style = MaterialTheme.typography.labelMedium)
            LinearProgressIndicator(
                progress = { level },
                modifier = Modifier.fillMaxWidth().height(7.dp).clip(RoundedCornerShape(99.dp)),
                color = PastelBlueDark,
                trackColor = PastelBlueMain.copy(alpha = 0.35f),
            )
        }
    }
}

@Composable
private fun SensorCard(label: String, value: String, icon: androidx.compose.ui.graphics.vector.ImageVector, modifier: Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = SurfaceWhite), elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) {
        Column(modifier = Modifier.padding(12.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Icon(icon, contentDescription = null, tint = PastelBlueDark, modifier = Modifier.size(19.dp))
            Text(value, color = PastelBlueDark, fontSize = 13.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
            Text(label, color = SoftText, fontSize = 10.sp, textAlign = TextAlign.Center)
        }
    }
}

@Composable
private fun EventsCard(events: List<CryEventDto>) {
    Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = SurfaceWhite), elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Ocorrências recentes", color = PastelBlueDark, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            if (events.isEmpty()) {
                Text("Nenhuma ocorrência registrada.", color = SoftText, style = MaterialTheme.typography.bodySmall)
            } else {
                events.take(5).forEach { event ->
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text(labelFor(event.label), color = SoftText, fontWeight = FontWeight.SemiBold)
                        Text("${(event.confidence * 100).toInt()}%", color = PastelBlueDark, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun EndpointDialog(currentEndpoint: String, onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var value by remember { mutableStateOf(currentEndpoint) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Conectar ao Raspberry") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Informe o IP e a porta do CrySense na mesma rede Wi-Fi.", color = SoftText)
                OutlinedTextField(value = value, onValueChange = { value = it }, singleLine = true, label = { Text("Ex.: 192.168.15.51:8080") })
            }
        },
        confirmButton = { TextButton(onClick = { onSave(normalizeEndpoint(value)) }) { Text("Salvar") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

private fun labelFor(label: String): String = when (label.lowercase()) {
    "cry" -> "Choro detectado"
    "noise" -> "Ruído ambiente"
    "colic" -> "Possível cólica"
    "hunger" -> "Possível fome"
    else -> "Monitoramento"
}

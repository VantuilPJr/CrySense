package com.vantuilpjunior.crysenseai.data.remote.local

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import okhttp3.MediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okio.BufferedSink
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.PUT
import retrofit2.http.Query
import java.io.IOException

const val DEFAULT_RASPBERRY_ENDPOINT = "http://192.168.15.51:8080"
const val FALLBACK_RASPBERRY_ENDPOINT = "http://10.42.0.1:8080"

data class PredictionDto(
    val label: String = "",
    val confidence: Double = 0.0,
)

data class PipelineDto(
    val phase: String = "idle",
    @SerializedName("trigger_ready") val triggerReady: Boolean = false,
    @SerializedName("type_ready") val typeReady: Boolean = false,
    @SerializedName("last_trigger") val lastTrigger: PredictionDto? = null,
    @SerializedName("last_type") val lastType: PredictionDto? = null,
    @SerializedName("last_error") val lastError: String? = null,
)

data class AudioDto(
    val running: Boolean = false,
    val listening: Boolean = false,
    @SerializedName("level_rms") val levelRms: Double? = null,
    @SerializedName("level_peak") val levelPeak: Double? = null,
    val error: String? = null,
)

data class CameraDto(
    val running: Boolean = false,
    val fps: Int = 0,
    val error: String? = null,
)

data class SensorDto(
    val temperature: Double? = null,
    val humidity: Double? = null,
    val pressure: Double? = null,
    val error: String? = null,
)

data class VisionDto(
    val connected: Boolean = false,
    val state: String = "offline",
    val alert: Boolean = false,
    val label: String? = null,
    val confidence: Double? = null,
    val detail: String? = null,
    val detections: List<VisionDetectionDto> = emptyList(),
)

data class VisionDetectionDto(
    val label: String = "",
    val confidence: Double = 0.0,
    val box: List<Double> = emptyList(),
)

data class RaspberryStatusDto(
    val ok: Boolean = false,
    val pipeline: PipelineDto = PipelineDto(),
    val audio: AudioDto = AudioDto(),
    val camera: CameraDto = CameraDto(),
    val sensor: SensorDto = SensorDto(),
    val vision: VisionDto = VisionDto(),
)

data class CryEventDto(
    val timestamp: String = "",
    val label: String = "",
    val confidence: Double = 0.0,
)

data class EventsDto(val events: List<CryEventDto> = emptyList())

data class TriggerConfirmationDto(
    val confirmed: Boolean = false,
    @SerializedName("positive_windows") val positiveWindows: Int = 0,
    @SerializedName("required_windows") val requiredWindows: Int = 3,
    @SerializedName("window_size") val windowSize: Int = 5,
)

data class AudioAnalysisDto(
    val filename: String = "",
    @SerializedName("duration_seconds") val durationSeconds: Double = 0.0,
    @SerializedName("sample_rate") val sampleRate: Int = 0,
    val trigger: PredictionDto = PredictionDto(),
    @SerializedName("trigger_confirmation")
    val triggerConfirmation: TriggerConfirmationDto = TriggerConfirmationDto(),
    val classification: PredictionDto? = null,
    @SerializedName("alert_triggered") val alertTriggered: Boolean = false,
    val message: String = "",
)

data class VisionConfigDto(
    @SerializedName("risk_zone") val riskZone: List<Double>? = null,
)

data class VisionZoneUpdateDto(
    @SerializedName("risk_zone") val riskZone: List<Double>?,
)

data class RaspberryMonitorState(
    val endpoint: String = DEFAULT_RASPBERRY_ENDPOINT,
    val status: RaspberryStatusDto = RaspberryStatusDto(),
    val events: List<CryEventDto> = emptyList(),
    val online: Boolean = false,
    val error: String? = null,
)

private interface RaspberryApi {
    @GET("api/status")
    suspend fun status(): RaspberryStatusDto

    @GET("api/events")
    suspend fun events(@Query("limit") limit: Int = 8): EventsDto

    @Multipart
    @POST("api/audio/analyze")
    suspend fun analyzeAudio(@Part audio: MultipartBody.Part): AudioAnalysisDto

    @GET("api/vision/config")
    suspend fun visionConfig(): VisionConfigDto

    @PUT("api/vision/config")
    suspend fun saveVisionConfig(@Body update: VisionZoneUpdateDto): VisionConfigDto
}

class RaspberryEndpointStore(context: Context) {
    private val preferences = context.getSharedPreferences("crysense_connection", Context.MODE_PRIVATE)

    fun load(): String = preferences.getString("raspberry_endpoint", DEFAULT_RASPBERRY_ENDPOINT)
        ?: DEFAULT_RASPBERRY_ENDPOINT

    fun save(endpoint: String) {
        preferences.edit().putString("raspberry_endpoint", normalizeEndpoint(endpoint)).apply()
    }
}

class RaspberryPiRepository {
    fun observe(endpoint: String): Flow<RaspberryMonitorState> = flow {
        val normalizedEndpoint = normalizeEndpoint(endpoint)

        while (currentCoroutineContext().isActive) {
            var connectedState: RaspberryMonitorState? = null
            for (candidateEndpoint in endpointCandidates(normalizedEndpoint)) {
                try {
                    val api = apiFor(candidateEndpoint)
                    val status = api.status()
                    val events = api.events().events
                    connectedState = RaspberryMonitorState(
                        endpoint = candidateEndpoint,
                        status = status,
                        events = events,
                        online = status.ok,
                    )
                    break
                } catch (_: Exception) {
                    // Tenta o endereço de emergência antes de sinalizar falha.
                }
            }
            if (connectedState != null) {
                emit(connectedState)
            } else {
                emit(
                    RaspberryMonitorState(
                        endpoint = normalizedEndpoint,
                        error = "Não foi possível conectar ao Raspberry. Verifique o Wi-Fi e o endereço.",
                    )
                )
            }
            delay(1_500)
        }
    }

    suspend fun analyzeAudio(context: Context, endpoint: String, uri: Uri): AudioAnalysisDto = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        val contentLength = resolver.openAssetFileDescriptor(uri, "r")?.use { it.length } ?: -1L
        if (contentLength > MAX_AUDIO_UPLOAD_BYTES) {
            throw IllegalArgumentException("O arquivo deve ter no máximo 12 MB.")
        }
        val fileName = resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        } ?: "audio.wav"
        if (!fileName.lowercase().endsWith(".wav")) {
            throw IllegalArgumentException("Selecione um arquivo WAV PCM (.wav).")
        }
        val body = ContentUriRequestBody(resolver = resolver, uri = uri, contentLength = contentLength)
        val part = MultipartBody.Part.createFormData("audio", fileName, body)
        apiFor(normalizeEndpoint(endpoint)).analyzeAudio(part)
    }

    suspend fun loadVisionZone(endpoint: String): List<Double>? = withContext(Dispatchers.IO) {
        apiFor(normalizeEndpoint(endpoint)).visionConfig().riskZone
    }

    suspend fun saveVisionZone(endpoint: String, zone: List<Double>): List<Double> = withContext(Dispatchers.IO) {
        require(zone.size == 4) { "A marcação da zona está inválida." }
        apiFor(normalizeEndpoint(endpoint)).saveVisionConfig(VisionZoneUpdateDto(zone)).riskZone
            ?: throw IOException("O Raspberry não confirmou a marcação da zona.")
    }

    suspend fun clearVisionZone(endpoint: String) = withContext(Dispatchers.IO) {
        apiFor(normalizeEndpoint(endpoint)).saveVisionConfig(VisionZoneUpdateDto(null))
    }
}

private fun apiFor(endpoint: String): RaspberryApi = Retrofit.Builder()
    .baseUrl("${endpoint.trimEnd('/')}/")
    .addConverterFactory(GsonConverterFactory.create())
    .build()
    .create(RaspberryApi::class.java)

private fun endpointCandidates(primary: String): List<String> =
    listOf(primary, FALLBACK_RASPBERRY_ENDPOINT).distinct()

private class ContentUriRequestBody(
    private val resolver: android.content.ContentResolver,
    private val uri: Uri,
    private val contentLength: Long,
) : RequestBody() {
    override fun contentType() = MediaType.parse("audio/wav")

    override fun contentLength(): Long = contentLength

    override fun writeTo(sink: BufferedSink) {
        resolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                sink.write(buffer, 0, read)
            }
        } ?: throw IOException("Não foi possível abrir o arquivo selecionado.")
    }
}

private const val MAX_AUDIO_UPLOAD_BYTES = 12L * 1024L * 1024L

fun normalizeEndpoint(endpoint: String): String {
    val trimmed = endpoint.trim().trimEnd('/')
    val withScheme = if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) trimmed else "http://$trimmed"
    return if (withScheme.isBlank() || withScheme == "http:") DEFAULT_RASPBERRY_ENDPOINT else withScheme
}

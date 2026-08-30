package com.vantuilpjunior.crysenseai

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.platform.LocalContext
import com.vantuilpjunior.crysenseai.data.local.HistoryManager
import com.vantuilpjunior.crysenseai.data.local.CryEvent
import com.vantuilpjunior.crysenseai.data.remote.local.RaspberryEndpointStore
import com.vantuilpjunior.crysenseai.data.remote.local.RaspberryMonitorState
import com.vantuilpjunior.crysenseai.data.remote.local.RaspberryPiRepository
import com.vantuilpjunior.crysenseai.data.remote.local.AudioAnalysisDto
import com.vantuilpjunior.crysenseai.ui.dashboard.LocalDashboardScreen
import com.vantuilpjunior.crysenseai.ui.theme.CrySenseAITheme
import com.vantuilpjunior.crysenseai.utils.NotificationHelper
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val repository = RaspberryPiRepository()
        val endpointStore = RaspberryEndpointStore(this)
        val notificationHelper = NotificationHelper(this)
        val historyManager = HistoryManager(this)

        val requestPermissionLauncher = registerForActivityResult(
            ActivityResultContracts.RequestPermission(),
        ) { }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            CrySenseAITheme {
                val context = LocalContext.current
                val coroutineScope = rememberCoroutineScope()
                var endpoint by rememberSaveable { mutableStateOf(endpointStore.load()) }
                var audioUploadInProgress by remember { mutableStateOf(false) }
                var audioUploadResult by remember { mutableStateOf<AudioAnalysisDto?>(null) }
                var audioUploadError by remember { mutableStateOf<String?>(null) }
                var visionZone by remember { mutableStateOf<List<Double>?>(null) }
                var visionZoneSaving by remember { mutableStateOf(false) }
                var visionZoneMessage by remember { mutableStateOf<String?>(null) }
                val audioPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
                    if (uri != null) {
                        coroutineScope.launch {
                            audioUploadInProgress = true
                            audioUploadResult = null
                            audioUploadError = null
                            try {
                                audioUploadResult = repository.analyzeAudio(context, endpoint, uri)
                            } catch (exception: Exception) {
                                audioUploadError = exception.message ?: "Não foi possível analisar o arquivo selecionado."
                            } finally {
                                audioUploadInProgress = false
                            }
                        }
                    }
                }
                val monitorState by produceState(
                    initialValue = RaspberryMonitorState(endpoint = endpoint),
                    key1 = endpoint,
                ) {
                    repository.observe(endpoint).collect { value = it }
                }
                LaunchedEffect(monitorState.endpoint, monitorState.online) {
                    if (!monitorState.online) return@LaunchedEffect
                    try {
                        visionZone = repository.loadVisionZone(monitorState.endpoint)
                        visionZoneMessage = null
                    } catch (exception: Exception) {
                        visionZoneMessage = exception.message ?: "Não foi possível carregar a marcação visual."
                    }
                }
                var lastAlertKey by remember { mutableStateOf("") }

                LaunchedEffect(monitorState.events.firstOrNull()?.timestamp) {
                    val latestEvent = monitorState.events.firstOrNull()
                    val confidence = ((latestEvent?.confidence ?: 0.0) * 100).toInt()
                    if (
                        latestEvent != null &&
                        latestEvent.label in setOf("colic", "hunger") &&
                        latestEvent.timestamp != lastAlertKey &&
                        confidence >= 75
                    ) {
                        lastAlertKey = latestEvent.timestamp
                        val event = CryEvent(
                            tipo = latestEvent.label.uppercase(),
                            confianca = confidence,
                            timestampMs = System.currentTimeMillis(),
                        )
                        historyManager.addEvent(event)
                        notificationHelper.showCryAlert(event.tipo, event.confianca)
                    }
                }

                LocalDashboardScreen(
                    state = monitorState,
                    endpoint = endpoint,
                    onEndpointChange = {
                        endpointStore.save(it)
                        endpoint = it
                    },
                    audioUploadInProgress = audioUploadInProgress,
                    audioUploadResult = audioUploadResult,
                    audioUploadError = audioUploadError,
                    onSelectAudio = { audioPicker.launch("audio/*") },
                    visionZone = visionZone,
                    visionZoneSaving = visionZoneSaving,
                    visionZoneMessage = visionZoneMessage,
                    onSaveVisionZone = { zone ->
                        coroutineScope.launch {
                            visionZoneSaving = true
                            visionZoneMessage = null
                            try {
                                visionZone = repository.saveVisionZone(monitorState.endpoint, zone)
                                visionZoneMessage = "Marcação salva. O monitor do PC aplica a área em até 2 segundos."
                            } catch (exception: Exception) {
                                visionZoneMessage = exception.message ?: "Não foi possível salvar a marcação."
                            } finally {
                                visionZoneSaving = false
                            }
                        }
                    },
                    onClearVisionZone = {
                        coroutineScope.launch {
                            visionZoneSaving = true
                            visionZoneMessage = null
                            try {
                                repository.clearVisionZone(monitorState.endpoint)
                                visionZone = null
                                visionZoneMessage = "Marcação removida. Desenhe uma nova área quando o berço estiver posicionado."
                            } catch (exception: Exception) {
                                visionZoneMessage = exception.message ?: "Não foi possível remover a marcação."
                            } finally {
                                visionZoneSaving = false
                            }
                        }
                    },
                )
            }
        }
    }
}

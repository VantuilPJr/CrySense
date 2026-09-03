package com.vantuilpjunior.crysenseai

import com.google.gson.Gson
import com.vantuilpjunior.crysenseai.data.remote.local.AudioAnalysisDto
import com.vantuilpjunior.crysenseai.data.remote.local.CryEventDto
import com.vantuilpjunior.crysenseai.data.remote.local.RaspberryStatusDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AudioDecisionTest {
    @Test
    fun serverConfirmedEventBelowOldThresholdStillNotifies() {
        val event = CryEventDto(
            timestamp = "2026-09-01T12:00:00Z",
            label = "colic",
            confidence = 0.693,
        )

        assertTrue(shouldNotifyCryEvent(event, lastAlertKey = ""))
        assertFalse(shouldNotifyCryEvent(event, lastAlertKey = event.timestamp))
    }

    @Test
    fun uploadResponseUsesServerAlertDecision() {
        val response = Gson().fromJson(
            """
            {
              "analysis_mode": "uploaded_known_cry",
              "ia1_bypassed": true,
              "classification": {"label": "colic", "confidence": 0.693},
              "alert_triggered": true,
              "message": "Alerta acionado"
            }
            """.trimIndent(),
            AudioAnalysisDto::class.java,
        )

        assertTrue(response.alertTriggered)
        assertTrue(response.ia1Bypassed)
        assertEquals("uploaded_known_cry", response.analysisMode)
        assertEquals("colic", response.classification?.label)
    }

    @Test
    fun realtimePipelineProgressAndInconclusiveDecisionAreOptionalAndParsed() {
        val response = Gson().fromJson(
            """
            {
              "ok": true,
              "pipeline": {
                "phase": "monitoring",
                "confirmation": {
                  "positive_windows": 2,
                  "required_windows": 3,
                  "window_size": 5,
                  "evaluated_windows": 4
                },
                "capture_progress": 0.5,
                "last_type_decision": {
                  "state": "inconclusive",
                  "timestamp": "2026-09-03T12:00:00Z",
                  "age_seconds": 1.5,
                  "attempt": 1,
                  "prediction": {"label": "hunger", "confidence": 0.6105},
                  "margin": 0.221,
                  "confidence_threshold": 0.68,
                  "margin_threshold": 0.20,
                  "reason": "low_confidence",
                  "retry_scheduled": true
                },
                "alert_latched": false,
                "episode_active": true
              }
            }
            """.trimIndent(),
            RaspberryStatusDto::class.java,
        )

        assertEquals(2, response.pipeline.confirmation?.positiveWindows)
        assertEquals(4, response.pipeline.confirmation?.evaluatedWindows)
        assertEquals(0.5, response.pipeline.captureProgress ?: 0.0, 0.0001)
        assertEquals("inconclusive", response.pipeline.lastTypeDecision?.state)
        assertEquals("hunger", response.pipeline.lastTypeDecision?.prediction?.label)
        assertEquals(0.68, response.pipeline.lastTypeDecision?.confidenceThreshold ?: 0.0, 0.0001)
        assertTrue(response.pipeline.lastTypeDecision?.retryScheduled == true)
        assertFalse(response.pipeline.alertLatched == true)
    }

    @Test
    fun legacyPipelineResponseRemainsCompatible() {
        val response = Gson().fromJson(
            """{"ok":true,"pipeline":{"phase":"monitoring"}}""",
            RaspberryStatusDto::class.java,
        )

        assertEquals("monitoring", response.pipeline.phase)
        assertNull(response.pipeline.confirmation)
        assertNull(response.pipeline.lastTypeDecision)
    }
}

package com.vantuilpjunior.crysenseai

import com.google.gson.Gson
import com.vantuilpjunior.crysenseai.data.remote.local.AudioAnalysisDto
import com.vantuilpjunior.crysenseai.data.remote.local.CryEventDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
}

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
              "trigger": {"label": "cry", "confidence": 0.966},
              "trigger_confirmation": {
                "confirmed": true,
                "positive_windows": 3,
                "required_windows": 3,
                "window_size": 5
              },
              "classification": {"label": "colic", "confidence": 0.693},
              "alert_triggered": true,
              "message": "Alerta acionado"
            }
            """.trimIndent(),
            AudioAnalysisDto::class.java,
        )

        assertTrue(response.alertTriggered)
        assertTrue(response.triggerConfirmation.confirmed)
        assertEquals(3, response.triggerConfirmation.positiveWindows)
        assertEquals("colic", response.classification?.label)
    }
}

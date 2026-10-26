package com.ordrnow.personal_agent_mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

/**
 * Keeps the voice call alive while the screen is off.
 *
 * Without this, Android Doze suspends the app's CPU and network shortly after
 * the screen turns off, and the WebRTC session (Vapi/Daily) drops — the bug
 * reported on an older phone. A foreground service with the microphone type
 * plus a PARTIAL_WAKE_LOCK keeps CPU and network available for the call; the
 * ongoing notification makes the state visible to the user.
 *
 * Started from Dart (VapiSessionController) on `call-start` — by then the Vapi
 * SDK has obtained the RECORD_AUDIO permission, which Android 14 requires
 * before a microphone-type foreground service may start.
 */
class VoiceCallService : Service() {
    companion object {
        private const val CHANNEL_ID = "voice_call"
        private const val NOTIFICATION_ID = 4711
        private const val WAKE_LOCK_TAG = "personal_agent:voice_call"
        // Safety net: never hold the CPU awake forever if stopping is missed.
        private const val WAKE_LOCK_TIMEOUT_MS = 4 * 60 * 60 * 1000L

        fun start(context: Context) {
            val intent = Intent(context, VoiceCallService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, VoiceCallService::class.java))
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        acquireWakeLock()
        createChannel()
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        releaseWakeLock()
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG)
            .apply {
                setReferenceCounted(false)
                acquire(WAKE_LOCK_TIMEOUT_MS)
            }
    }

    private fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Voice call",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shown while a voice call with your assistant is active"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Voice call active")
            .setContentText("The assistant is still listening with the screen off")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
}

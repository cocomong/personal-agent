import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/transcript_entry.dart';

/// Survives process death.
///
/// Android routinely kills a backgrounded app (Samsung's sleeping-apps policy,
/// Doze, memory pressure while Chrome renders the invoice-style preview page).
/// Without this, a relaunch — including one triggered by the
/// `personalagent://app` deep link — starts a brand-new conversation: the
/// server-side chat chain resets (the chat id lived in memory) and the
/// transcript is empty, which reads as "the app restarted".
///
/// Everything here is best-effort: a storage failure must never break chat.
class SessionPersistence {
  SessionPersistence({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  /// Shared instance used by the controllers by default.
  static final SessionPersistence instance = SessionPersistence();

  static const _chatIdKey = 'pa.chat_id_v1';
  static const _transcriptKey = 'pa.transcript_v1';

  /// Keep the newest N turns — enough to restore context without unbounded
  /// growth in encrypted prefs.
  static const _maxEntries = 100;

  final FlutterSecureStorage _storage;

  Future<String?> loadChatId() async {
    try {
      final id = await _storage.read(key: _chatIdKey);
      return (id == null || id.isEmpty) ? null : id;
    } catch (_) {
      return null;
    }
  }

  Future<void> saveChatId(String? id) async {
    try {
      if (id == null || id.isEmpty) {
        await _storage.delete(key: _chatIdKey);
      } else {
        await _storage.write(key: _chatIdKey, value: id);
      }
    } catch (_) {
      // best-effort
    }
  }

  Future<List<TranscriptEntry>> loadTranscript() async {
    try {
      final raw = await _storage.read(key: _transcriptKey);
      if (raw == null || raw.isEmpty) return const [];
      final decoded = jsonDecode(raw);
      if (decoded is! List) return const [];
      return decoded
          .whereType<Map>()
          .map((m) => TranscriptEntry.fromJson(m.cast<String, dynamic>()))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> saveTranscript(List<TranscriptEntry> entries) async {
    try {
      // 'system' entries are UI notices (e.g. "call ended"), not conversation.
      final capped = entries
          .where((e) => e.role != 'system')
          .take(_maxEntries)
          .map((e) => e.toJson())
          .toList();
      await _storage.write(key: _transcriptKey, value: jsonEncode(capped));
    } catch (_) {
      // best-effort
    }
  }

  /// Sign-out: forget the conversation entirely (tokens are cleared by
  /// SessionStore).
  Future<void> clear() async {
    try {
      await _storage.delete(key: _chatIdKey);
      await _storage.delete(key: _transcriptKey);
    } catch (_) {
      // best-effort
    }
  }
}

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/session_store.dart';
import '../config.dart';
import 'session_persistence.dart';

/// Text-chat channel (ADR: voice = Vapi call session; text = Vapi /chat via
/// the n8n proxy webhook). Silent by design — no audio session, no TTS.
/// Multi-turn context is kept server-side through Vapi's chat id chain, which
/// the proxy returns after every turn.
///
/// The chat id is PERSISTED (SessionPersistence): Android kills backgrounded
/// apps routinely, and without this a relaunch silently starts a new
/// conversation chain.
class ChatController {
  ChatController({SessionPersistence? persistence})
      : _persistence = persistence ?? SessionPersistence.instance;

  final SessionPersistence _persistence;
  String? _chatId;
  bool _chatIdLoaded = false;

  /// Sends one typed turn and returns the assistant's final reply text.
  /// Throws [ChatException] with a user-presentable message on failure.
  Future<String> send(String text) async {
    if (!_chatIdLoaded) {
      _chatId ??= await _persistence.loadChatId();
      _chatIdLoaded = true;
    }
    final body = <String, dynamic>{'input': text};
    if (_chatId != null && _chatId!.isNotEmpty) body['chatId'] = _chatId!;

    final headers = {'Content-Type': 'application/json'};
    final sessionToken = SessionStore.instance.token;
    if (sessionToken != null && sessionToken.isNotEmpty) {
      headers['X-User-Token'] = sessionToken;
    }

    final resp = await http
        .post(Uri.parse('$n8nBaseUrl/webhook/chat'),
            headers: headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 180));

    Map<String, dynamic> data;
    try {
      data = jsonDecode(resp.body) as Map<String, dynamic>;
    } catch (_) {
      throw ChatException('The assistant did not respond (${resp.statusCode}).');
    }
    if (resp.statusCode != 200) {
      throw ChatException(
          data['error'] is String ? data['error'] as String : 'Chat failed.');
    }
    final chatId = data['chatId'];
    if (chatId is String && chatId.isNotEmpty) {
      _chatId = chatId;
      // Persist so a relaunch (including via the personalagent:// deep link
      // after Android killed us) continues the same conversation chain.
      unawaited(_persistence.saveChatId(chatId));
    }
    final reply = data['reply'];
    if (reply is String && reply.isNotEmpty) return reply;
    throw ChatException('No reply received. Please try again.');
  }

  /// Starts a fresh conversation chain (clears the server-side chat id and
  /// the persisted copy).
  void reset() {
    _chatId = null;
    _chatIdLoaded = true;
    unawaited(_persistence.saveChatId(null));
  }
}

class ChatException implements Exception {
  ChatException(this.message);
  final String message;
  @override
  String toString() => message;
}

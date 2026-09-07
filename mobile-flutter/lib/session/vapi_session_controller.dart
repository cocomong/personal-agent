import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:vapi/vapi.dart';

import '../auth/session_store.dart';
import '../config.dart';

/// Call session state surfaced to the UI.
enum SessionStatus { disconnected, connecting, connected }

/// Wraps the Vapi Flutter SDK (`VapiClient` / `VapiCall`) for a single
/// voice + same-session text call (ADR-8 / ADR-9).
///
/// `start` drives voice; `sendUserText` injects a typed turn on the SAME call
/// so the agent keeps context across speak-or-type. ElevenLabs is the voice
/// engine (assistant `voice.provider='11labs'`).
class VapiSessionController extends ChangeNotifier {
  VapiClient? _client;
  VapiCall? _call;
  StreamSubscription<VapiEvent>? _subscription;
  SessionStatus _status = SessionStatus.disconnected;

  /// Called when the assistant produces a finalized transcript turn
  /// (spoken or typed) on the shared session.
  void Function(String text)? onAgentTranscript;

  SessionStatus get status => _status;
  bool get isConnected => _status == SessionStatus.connected;

  Future<void> init() async {
    if (_client != null) return;
    await VapiClient.platformInitialized.future;
    _client = VapiClient(vapiPublicKey);
  }

  Future<void> start() async {
    await init();
    await stop();
    _lastAgentText = null; // new session: allow an identical reply again
    final overrides = await _fetchSessionOverrides();
    final call = await _client!.start(
      assistantId: vapiAssistantId,
      assistantOverrides: overrides,
    );
    _call = call;
    _subscription = call.onEvent.listen(_handleEvent);
    _status = SessionStatus.connecting;
    notifyListeners();
  }

  /// Fetch per-call assistant overrides (setup-status variables + dynamic
  /// greeting) from the n8n call-start hook. Web calls don't trigger a
  /// server-side assistant-request, so the client must pass them in.
  /// Falls back to an empty overrides map (plain stored assistant) if the
  /// hook is unreachable, so calls still work.
  Future<Map<String, dynamic>> _fetchSessionOverrides() async {
    try {
      final headers = {'Content-Type': 'application/json'};
      final sessionToken = SessionStore.instance.token;
      if (sessionToken != null && sessionToken.isNotEmpty) {
        headers['X-User-Token'] = sessionToken;
      }
      final resp = await http
          .post(Uri.parse(vapiSessionHookUrl),
              headers: headers, body: '{}')
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode != 200) return const {};
      final body = jsonDecode(resp.body) as Map<String, dynamic>;
      final overrides = body['assistantOverrides'];
      return overrides is Map<String, dynamic> ? overrides : const {};
    } catch (_) {
      return const {};
    }
  }

  Future<void> sendUserText(String content) async {
    _lastAgentText = null; // new user turn: same reply text must not dedupe
    await _call?.send({
      'type': 'add-message',
      'message': {'role': 'user', 'content': content},
    });
  }

  void setMuted(bool muted) {
    _call?.setMuted(muted);
  }

  Future<void> stop() async {
    await _call?.stop();
    _call = null;
    await _subscription?.cancel();
    _subscription = null;
    _status = SessionStatus.disconnected;
    notifyListeners();
  }

  void _handleEvent(VapiEvent event) {
    switch (event.label) {
      case 'call-start':
        _status = SessionStatus.connected;
        notifyListeners();
        break;
      case 'call-end':
        _status = SessionStatus.disconnected;
        notifyListeners();
        break;
      case 'message':
        _handleMessage(event.value);
        break;
    }
  }

  /// Surfaces finalized assistant text (spoken OR typed) on the shared
  /// session. Two event shapes reach us:
  ///   - voice: type 'transcript', transcriptType 'final', role 'assistant',
  ///     text under 'transcript';
  ///   - text chat: type 'message', role 'assistant', text under 'content'
  ///     (String, or a List of {type:'text', text:...} parts).
  /// Text replies can arrive through either/both shapes per turn, so the last
  /// emitted text is remembered and duplicates are dropped.
  String? _lastAgentText;

  void _handleMessage(dynamic value) {
    if (value is! Map) return;
    String? text;
    if (value['type'] == 'transcript') {
      if (value['transcriptType'] != 'final') return;
      if (value['role'] != 'assistant') return;
      final t = value['transcript'];
      if (t is String) text = t;
    } else if (value['type'] == 'message' &&
        (value['role'] == 'assistant' || value['role'] == 'agent')) {
      text = _textFromContent(value['content']);
    }
    if (text == null || text.trim().isEmpty) return;
    final trimmed = text.trim();
    if (trimmed == _lastAgentText) return; // same turn emitted twice
    _lastAgentText = trimmed;
    onAgentTranscript?.call(trimmed);
  }

  /// 'content' arrives as a plain String or as a List of content parts
  /// (e.g. [{type:'text', text:'...'}]). Returns the concatenated text.
  String? _textFromContent(dynamic content) {
    if (content is String) return content;
    if (content is List) {
      final parts = <String>[];
      for (final c in content) {
        if (c is Map) {
          final t = c['text'];
          if (t is String && t.isNotEmpty) parts.add(t);
        } else if (c is String && c.isNotEmpty) {
          parts.add(c);
        }
      }
      return parts.isEmpty ? null : parts.join('\n');
    }
    return null;
  }

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    _call?.dispose();
    _client?.dispose();
    super.dispose();
  }
}


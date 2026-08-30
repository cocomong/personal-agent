import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:vapi/vapi.dart';

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
      final resp = await http
          .post(Uri.parse(vapiSessionHookUrl),
              headers: {'Content-Type': 'application/json'}, body: '{}')
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

  /// Surface finalized assistant transcript turns (Vapi `message` events of
  /// `type: 'transcript'`, `transcriptType: 'final'`, `role: 'assistant'`).
  void _handleMessage(dynamic value) {
    if (value is! Map) return;
    if (value['type'] != 'transcript') return;
    if (value['transcriptType'] != 'final') return;
    if (value['role'] != 'assistant') return;
    final text = value['transcript'];
    if (text is String && text.isNotEmpty) {
      onAgentTranscript?.call(text);
    }
  }

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    _call?.dispose();
    _client?.dispose();
    super.dispose();
  }
}


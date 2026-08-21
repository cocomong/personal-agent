import 'dart:async';

import 'package:flutter/foundation.dart';
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
    final call = await _client!.start(assistantId: vapiAssistantId);
    _call = call;
    _subscription = call.onEvent.listen(_handleEvent);
    _status = SessionStatus.connecting;
    notifyListeners();
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


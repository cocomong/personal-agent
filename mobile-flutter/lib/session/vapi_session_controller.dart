import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:vapi/vapi.dart';

import '../auth/session_store.dart';
import '../config.dart';
import 'foreground_call_service.dart';

/// Call session state surfaced to the UI.
enum SessionStatus { disconnected, connecting, connected }

/// Builds the Vapi client the controller talks to. Test seam: production
/// leaves this null and [VapiSessionController.init] creates the real SDK
/// client; tests inject a fake so no platform channel is ever touched.
typedef VapiClientFactory = VapiClientInterface Function();

/// Fetches the per-call assistant overrides. Test seam: production leaves
/// this null and the n8n call-start hook is used.
typedef OverridesFetcher = Future<Map<String, dynamic>> Function();

/// Wraps the Vapi Flutter SDK (`VapiClient` / `VapiCall`) for a single
/// voice + same-session text call (ADR-8 / ADR-9).
///
/// `start` drives voice; `sendUserText` injects a typed turn on the SAME call
/// so the agent keeps context across speak-or-type. ElevenLabs is the voice
/// engine (assistant `voice.provider='11labs'`).
///
/// Concurrency contract (added after the double-tap bug seen on a slow
/// phone, where two rapid taps made two assistants talk over each other):
/// - `start` is single-flight: a second `start` while one is still
///   connecting joins the in-flight attempt instead of creating a second
///   concurrent call.
/// - `stop` during a connecting `start` supersedes it: when the SDK call
///   completes afterwards it is torn down immediately, never orphaned.
class VapiSessionController extends ChangeNotifier {
  VapiSessionController({
    VapiClientFactory? clientFactory,
    OverridesFetcher? overridesFetcher,
  })  : _clientFactory = clientFactory,
        _overridesFetcher = overridesFetcher;

  final VapiClientFactory? _clientFactory;
  final OverridesFetcher? _overridesFetcher;

  VapiClientInterface? _client;
  VapiCall? _call;
  StreamSubscription<VapiEvent>? _subscription;
  SessionStatus _status = SessionStatus.disconnected;

  /// The in-flight [start] attempt, if any. Further starts join it.
  Future<void>? _starting;

  /// Bumped by every [stop] and [dispose]. A [start] snapshots it before its
  /// network work; if the number has moved by the time the SDK call returns,
  /// that start was superseded and its call gets torn down.
  int _stopGeneration = 0;

  /// Called when the assistant produces a finalized transcript turn
  /// (spoken or typed) on the shared session.
  void Function(String text)? onAgentTranscript;

  SessionStatus get status => _status;
  bool get isConnected => _status == SessionStatus.connected;

  Future<void> init() async {
    if (_client != null) return;
    final clientFactory = _clientFactory;
    if (clientFactory != null) {
      _client = clientFactory();
      return;
    }
    await VapiClient.platformInitialized.future;
    _client = VapiClient(vapiPublicKey);
  }

  /// Starts the voice call. Single-flight: while a previous start is still
  /// connecting (hook fetch + WebRTC negotiation — seconds on a slow phone),
  /// further starts await the same future instead of starting more calls,
  /// so rapid double-taps can no longer create overlapping assistants.
  Future<void> start() async {
    final starting = _starting;
    if (starting != null) return starting;
    return _starting = _start().whenComplete(() => _starting = null);
  }

  Future<void> _start() async {
    await init();
    if (_status != SessionStatus.disconnected) return; // already up/upcoming

    final generation = _stopGeneration;
    _lastAgentText = null; // new session: allow an identical reply again

    // Clear any call object a 'call-end' event left behind before
    // reconnecting (call-end flips status but keeps _call set).
    await _call?.stop();
    _call = null;
    await _subscription?.cancel();
    _subscription = null;

    _status = SessionStatus.connecting; // visible BEFORE the network work
    notifyListeners();

    final VapiCall call;
    try {
      final fetchOverrides = _overridesFetcher ?? _fetchSessionOverrides;
      final overrides = await fetchOverrides();
      call = await _client!.start(
        assistantId: vapiAssistantId,
        assistantOverrides: overrides,
      );
    } catch (_) {
      if (_stopGeneration == generation) {
        _status = SessionStatus.disconnected;
        notifyListeners();
      }
      rethrow;
    }

    if (_stopGeneration != generation) {
      // A stop (mode switch to text, screen change, dispose) superseded
      // this start while it was connecting. Tear the fresh call down
      // instead of leaving a live assistant nobody is listening to.
      await call.stop();
      call.dispose();
      return;
    }

    _call = call;
    _subscription = call.onEvent.listen(_handleEvent);
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

  /// Make the assistant speak a fixed line right now — Vapi's `say` control
  /// message, so it costs no model turn and cannot improvise. Used when the
  /// app is backgrounded mid-call (see AgentScreen's lifecycle nudge).
  Future<void> say(String text) async {
    if (_call == null || _status != SessionStatus.connected) return;
    await _call!.send({'type': 'say', 'message': text});
  }

  Future<void> stop() async {
    _stopGeneration++; // supersede any start still connecting
    unawaited(ForegroundCallService.stop());
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
        // Keep the call alive when the screen turns off (Android Doze would
        // otherwise suspend the process and drop the WebRTC session). Started
        // here, after the SDK obtained RECORD_AUDIO — Android 14 requires the
        // permission before a microphone-type foreground service may start.
        unawaited(ForegroundCallService.start());
        notifyListeners();
        break;
      case 'call-end':
        _status = SessionStatus.disconnected;
        unawaited(ForegroundCallService.stop());
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
    _stopGeneration++; // an in-flight start must self-destruct, not assign
    unawaited(ForegroundCallService.stop());
    unawaited(_subscription?.cancel());
    _call?.dispose();
    _client?.dispose();
    super.dispose();
  }
}

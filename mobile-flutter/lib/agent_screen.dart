import 'dart:async';

import 'package:flutter/material.dart';

import '../models/transcript_entry.dart';
import '../session/call_state_service.dart';
import '../session/chat_controller.dart';
import '../session/session_persistence.dart';
import '../session/vapi_session_controller.dart';

/// Voice is primary, text is a fallback (ADR-8). Both run on ONE Vapi call
/// session (VapiSessionController), so the agent keeps context across
/// speak-or-type turns.
class AgentScreen extends StatefulWidget {
  const AgentScreen(
      {super.key, this.onSignOut, this.chat, this.session, this.callState});

  /// Optional: called when the user taps the sign-out button (auth gate).
  final VoidCallback? onSignOut;

  /// Optional: inject a ChatController (test seam — widget tests pass a fake).
  final ChatController? chat;

  /// Optional: inject a VapiSessionController (test seam, same pattern as
  /// [chat]) — widget tests pass one wired to a fake Vapi client.
  final VapiSessionController? session;

  /// Optional: inject the server-side call-state lookup (test seam).
  final CallStateService? callState;

  @override
  State<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends State<AgentScreen>
    with WidgetsBindingObserver {
  late final VapiSessionController _session =
      widget.session ?? VapiSessionController();
  late final ChatController _chat = widget.chat ?? ChatController();
  final _transcript = <TranscriptEntry>[];
  final _draftController = TextEditingController();

  bool _voiceMode = true;
  int _nextId = 0;

  /// Background nudge: when the app is paused mid-call the assistant is still
  /// listening (and billing). After 6 s say something so the user knows the
  /// session is live and can hang up on purpose. One nudge per excursion.
  Timer? _nudgeTimer;
  bool _nudgedThisExcursion = false;
  static const _nudgeDelay = Duration(seconds: 6);

  /// A call that is still open on Vapi's side while this app has no live call
  /// object (process restarted, or the WebRTC leg dropped). Starting another
  /// would put a second assistant on the line, so Start Voice is disabled
  /// until the server says the call is gone.
  late final CallStateService _callState =
      widget.callState ?? const CallStateService();
  bool _remoteCallActive = false;
  Timer? _callStatePoll;
  static const _callStatePollInterval = Duration(seconds: 15);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _session.addListener(_onSessionChanged);
    _session.onAgentTranscript = _onAgentTranscript;
    _restoreTranscript();
    _refreshCallState();
  }

  /// Ask the backend whether a call is still open (see CallStateService).
  /// While one is, poll until it closes so the button re-enables by itself.
  Future<void> _refreshCallState() async {
    if (_session.isConnected) {
      if (_remoteCallActive) setState(() => _remoteCallActive = false);
      return;
    }
    final active = await _callState.isCallActive();
    if (!mounted) return;
    if (active != _remoteCallActive) setState(() => _remoteCallActive = active);
    _callStatePoll?.cancel();
    if (active) {
      _callStatePoll = Timer(_callStatePollInterval, _refreshCallState);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _scheduleNudge();
    } else if (state == AppLifecycleState.resumed) {
      _nudgeTimer?.cancel();
      _nudgedThisExcursion = false;
      _refreshCallState();
    }
  }

  void _scheduleNudge() {
    if (!_session.isConnected || _nudgedThisExcursion) return;
    _nudgeTimer?.cancel();
    _nudgeTimer = Timer(_nudgeDelay, () {
      if (!mounted || !_session.isConnected || _nudgedThisExcursion) return;
      _nudgedThisExcursion = true;
      unawaited(_session.say(_nudgeText()));
    });
  }

  /// Context first: if the assistant just offered the invoice styles, prompt
  /// for the choice; otherwise ask whether to hang up.
  String _nudgeText() {
    for (final e in _transcript) {
      if (e.role != 'agent') continue;
      final t = e.text.toLowerCase();
      if (t.contains('style') || t.contains('template')) {
        return 'Take your time — tell me which style you like, or tap it on your phone.';
      }
      break;
    }
    return "I'm still here — should I hang up?";
  }

  /// Android kills backgrounded apps routinely; the transcript is restored
  /// from disk so a relaunch (also via the personalagent:// deep link) shows
  /// the previous conversation instead of an empty screen.
  ///
  /// A restored transcript is NOT a restored call: a voice session is a live
  /// WebRTC call and dies with the process. Say so, otherwise the enabled
  /// "Start Voice" button looks like the app lost track of a call it was in.
  Future<void> _restoreTranscript() async {
    final saved = await SessionPersistence.instance.loadTranscript();
    if (!mounted || saved.isEmpty) return;
    setState(() {
      _transcript
        ..clear()
        ..addAll(saved);
      _nextId = saved.length;
      if (saved.any((e) => e.isVoice)) {
        _transcript.insert(
          0,
          const TranscriptEntry(
            id: 'sys-restore',
            role: 'system',
            text: 'Conversation restored · the previous voice call is no longer '
                'connected to this app.',
            isVoice: false,
          ),
        );
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _nudgeTimer?.cancel();
    _callStatePoll?.cancel();
    _draftController.dispose();
    _session.removeListener(_onSessionChanged);
    _session.dispose();
    super.dispose();
  }

  void _onSessionChanged() => setState(() {});

  void _onAgentTranscript(String text) {
    _append(TranscriptEntry(
      id: _newId(),
      role: 'agent',
      text: text,
      isVoice: _voiceMode,
    ));
  }

  String _newId() => 'e${_nextId++}';

  void _append(TranscriptEntry entry) {
    setState(() => _transcript.insert(0, entry));
    unawaited(SessionPersistence.instance.saveTranscript(_transcript));
  }

  Future<void> _toggleVoice() async {
    if (_remoteCallActive) return; // still open on the server
    if (_session.isConnected) {
      await _session.stop();
      return;
    }
    if (_session.status == SessionStatus.connecting) {
      // A start is already in flight (the controller guard holds); a second
      // tap must do nothing, not queue another assistant.
      return;
    }
    await _session.start();
  }

  Future<void> _onSend() async {
    final text = _draftController.text.trim();
    if (text.isEmpty) return;
    _draftController.clear();
    _append(TranscriptEntry.fromInput(_newId(), text, isVoice: false));
    try {
      // Text mode talks to the assistant through the n8n chat proxy (Vapi
      // /chat): silent, server-side tool execution, no audio session.
      final reply = await _chat.send(text);
      if (reply.isNotEmpty) {
        _append(TranscriptEntry(
            id: _newId(), role: 'agent', text: reply, isVoice: false));
      }
    } catch (e) {
      final msg = e is ChatException ? e.message : 'Something went wrong sending that.';
      _append(TranscriptEntry(
          id: _newId(), role: 'agent', text: msg, isVoice: false));
    }
  }

  void _onModeChanged(bool voice) {
    setState(() => _voiceMode = voice);
    if (!voice && _session.isConnected) {
      // Switching to text: end the voice call (text is a separate session
      // and would otherwise keep reading replies aloud).
      unawaited(_session.stop());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: _ModeSwitch(
                        voiceMode: _voiceMode, onChanged: _onModeChanged),
                  ),
                  if (widget.onSignOut != null)
                    IconButton(
                      tooltip: 'Sign out',
                      onPressed: widget.onSignOut,
                      icon: const Icon(Icons.logout,
                          color: Color(0xFF94A3B8), size: 20),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Expanded(child: _TranscriptList(entries: _transcript)),
              const SizedBox(height: 12),
              _voiceMode ? _buildVoiceButton() : _buildTextInput(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVoiceButton() {
    final connected = _session.isConnected;
    final connecting = _session.status == SessionStatus.connecting;
    final blockedByRemote = _remoteCallActive && !connected && !connecting;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (blockedByRemote)
          const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: Text(
              'A voice call on this account is still open — it will close on '
              'its own in a moment.',
              key: ValueKey('remote-call-hint'),
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: Color(0xFF94A3B8), fontSize: 12, height: 1.35),
            ),
          ),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor:
                  blockedByRemote ? const Color(0xFF475569) : connected ? const Color(0xFFDC2626) : const Color(0xFF2563EB),
              padding: const EdgeInsets.symmetric(vertical: 16),
            ),
            // Disabled while connecting so a second tap can't even queue up;
            // the controller's single-flight guard is the real defense, this
            // is defense in depth. Also disabled while a call is still open on
            // the server but not attached to this app (would be a 2nd call).
            onPressed: connecting || blockedByRemote ? null : _toggleVoice,
            child: Text(
                blockedByRemote
                    ? 'Call in progress…'
                    : connecting
                        ? 'Connecting…'
                        : connected
                            ? 'End Voice'
                            : 'Start Voice',
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          ),
        ),
      ],
    );
  }

  Widget _buildTextInput() {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _draftController,
            style: const TextStyle(color: Color(0xFFF8FAFC)),
            decoration: const InputDecoration(
              hintText: 'Type a message…',
              hintStyle: TextStyle(color: Color(0xFF94A3B8)),
              filled: true,
              fillColor: Color(0xFF1E293B),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.all(Radius.circular(24)),
                borderSide: BorderSide.none,
              ),
            ),
            onSubmitted: (_) => _onSend(),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: _onSend,
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF2563EB),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          ),
          child: const Text('Send', style: TextStyle(fontWeight: FontWeight.w600)),
        ),
      ],
    );
  }
}

class _ModeSwitch extends StatelessWidget {
  const _ModeSwitch({required this.voiceMode, required this.onChanged});

  final bool voiceMode;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return SegmentedButton<bool>(
      segments: const [
        ButtonSegment(value: true, label: Text('Voice')),
        ButtonSegment(value: false, label: Text('Text')),
      ],
      selected: {voiceMode},
      onSelectionChanged: (s) => onChanged(s.first),
    );
  }
}

class _TranscriptList extends StatelessWidget {
  const _TranscriptList({required this.entries});

  final List<TranscriptEntry> entries;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      reverse: true,
      itemCount: entries.length,
      itemBuilder: (context, i) {
        final e = entries[i];
        if (e.role == 'system') {
          // UI notice (e.g. "conversation restored, call ended") — no bubble.
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
            child: Text(
              e.text,
              key: ValueKey(e.id),
              textAlign: TextAlign.center,
              style: const TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 12,
                  fontStyle: FontStyle.italic,
                  height: 1.35),
            ),
          );
        }
        final isUser = e.role == 'user';
        return Align(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            constraints: const BoxConstraints(maxWidth: 320),
            decoration: BoxDecoration(
              color: isUser ? const Color(0xFF2563EB) : const Color(0xFF334155),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(e.text, style: const TextStyle(color: Color(0xFFF8FAFC), fontSize: 15)),
                const SizedBox(height: 2),
                Text(e.isVoice ? 'voice' : 'text',
                    style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11)),
              ],
            ),
          ),
        );
      },
    );
  }
}

import 'package:flutter/material.dart';

import '../models/transcript_entry.dart';
import '../session/vapi_session_controller.dart';

/// Voice is primary, text is a fallback (ADR-8). Both run on ONE Vapi call
/// session (VapiSessionController), so the agent keeps context across
/// speak-or-type turns.
class AgentScreen extends StatefulWidget {
  const AgentScreen({super.key});

  @override
  State<AgentScreen> createState() => _AgentScreenState();
}

class _AgentScreenState extends State<AgentScreen> {
  final VapiSessionController _session = VapiSessionController();
  final _transcript = <TranscriptEntry>[];
  final _draftController = TextEditingController();

  bool _voiceMode = true;
  int _nextId = 0;

  @override
  void initState() {
    super.initState();
    _session.addListener(_onSessionChanged);
    _session.onAgentTranscript = _onAgentTranscript;
  }

  @override
  void dispose() {
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
  }

  Future<void> _toggleVoice() async {
    if (_session.isConnected) {
      await _session.stop();
      return;
    }
    await _session.start();
  }

  Future<void> _onSend() async {
    final text = _draftController.text.trim();
    if (text.isEmpty) return;
    _draftController.clear();
    _append(TranscriptEntry.fromInput(_newId(), text, isVoice: false));
    await _session.sendUserText(text);
  }

  void _onModeChanged(bool voice) {
    setState(() => _voiceMode = voice);
    // Mute the mic while typing so it is not read as speech (same-session).
    _session.setMuted(!voice);
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
              _ModeSwitch(voiceMode: _voiceMode, onChanged: _onModeChanged),
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
    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: connected ? const Color(0xFFDC2626) : const Color(0xFF2563EB),
          padding: const EdgeInsets.symmetric(vertical: 16),
        ),
        onPressed: _toggleVoice,
        child: Text(connected ? 'End Voice' : 'Start Voice',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
      ),
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

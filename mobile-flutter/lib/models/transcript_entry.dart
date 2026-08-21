/// A single turn in the shared voice+text conversation.
class TranscriptEntry {
  const TranscriptEntry({
    required this.id,
    required this.role,
    required this.text,
    required this.isVoice,
  });

  final String id;
  final String role; // 'user' | 'agent'
  final String text;
  final bool isVoice;

  TranscriptEntry.fromInput(this.id, this.text, {required this.isVoice}) : role = 'user';
}

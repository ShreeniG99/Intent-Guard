import { useState, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ActivityIndicator,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { AgentStackParamList } from '../navigation/RootNavigator';
import { colors, spacing, radii, type } from '../theme';
import { parseOrderText, startAgentRun } from '../api/client';
import { KNOWN_PRODUCTS } from '../api/types';

type Props = NativeStackScreenProps<AgentStackParamList, 'AgentChat'>;

interface ChatMessage {
  id: string;
  from: 'user' | 'agent';
  text: string;
}

const WELCOME: ChatMessage = {
  id: 'welcome',
  from: 'agent',
  text:
    "Heyyaa, I'm your shopping agent, Harsha. Welcome to IntentGuard. Tell me what to buy - " +
    "the product, model name, qty and price range - and I'll browse the store, check it against " +
    "your intent and only pay if it's safe.",
};

export default function AgentScreen({ navigation }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, from: 'user', text };
    setMessages((prev) => [...prev, userMsg]);

    const parsed = parseOrderText(text);
    if (!parsed) {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          from: 'agent',
          text: `I can currently only shop for: ${KNOWN_PRODUCTS.map((p) => p.name).join(', ')}. Try mentioning one of those and a max price.`,
        },
      ]);
      return;
    }

    setSending(true);
    setMessages((prev) => [
      ...prev,
      { id: `a-thinking-${Date.now()}`, from: 'agent', text: `On it - checking out up to ₹${parsed.max_price} for you.` },
    ]);
    try {
      const { run_id } = await startAgentRun(parsed);
      const product = KNOWN_PRODUCTS.find((p) => p.id === parsed.product)!.name;
      navigation.navigate('LiveRun', { runId: run_id, product });
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, from: 'agent', text: `Couldn't start that run: ${e.message}` },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Image source={require('../../assets/shopping_assistant.jpg')} style={styles.avatarImage} resizeMode="cover" />
        </View>
        <View>
          <Text style={styles.headerTitle}>Shopping Agent</Text>
          <Text style={styles.headerSubtitle}>Online</Text>
        </View>
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          style={styles.flex}
          contentContainerStyle={styles.messages}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          renderItem={({ item }) => (
            <View style={[styles.bubble, item.from === 'user' ? styles.bubbleUser : styles.bubbleAgent]}>
              <Text style={item.from === 'user' ? styles.bubbleTextUser : styles.bubbleTextAgent}>{item.text}</Text>
            </View>
          )}
        />

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            placeholder="Type your order..."
            placeholderTextColor={colors.textSecondary}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={send}
            editable={!sending}
          />
          <Pressable onPress={send} style={styles.sendBtn} disabled={sending}>
            {sending ? (
              <ActivityIndicator color={colors.white} size="small" />
            ) : (
              <Ionicons name="arrow-up" size={20} color={colors.white} />
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.white,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: radii.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
    overflow: 'hidden',
  },
  avatarImage: { width: '100%', height: '100%' },
  headerTitle: { ...type.h3, color: colors.textPrimary },
  headerSubtitle: { ...type.caption, color: colors.allow },
  messages: { padding: spacing.lg, gap: spacing.sm },
  bubble: { maxWidth: '82%', padding: spacing.md, borderRadius: radii.lg },
  bubbleAgent: { backgroundColor: colors.white, alignSelf: 'flex-start', borderBottomLeftRadius: radii.sm },
  bubbleUser: { backgroundColor: colors.primary, alignSelf: 'flex-end', borderBottomRightRadius: radii.sm },
  bubbleTextAgent: { ...type.body, color: colors.textPrimary },
  bubbleTextUser: { ...type.body, color: colors.white },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    backgroundColor: colors.white,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: colors.greyLight,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    ...type.body,
    color: colors.textPrimary,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: radii.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

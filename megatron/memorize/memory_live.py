import torch

class MemoryLive:
    """
    Represents a sliding window of memories tracked for a particular model.
    """

    def __init__(self, device, memory_size, memory_invalid_query_mode, memory_dumper_init=None):
        """
        memory_size:
            Number of key/value pairs (per batch & attention head) to retain

        memory_invalid_query_mode:
            How to populate the memory attention mask for queries that are past an EOD token in the
            current context and thus shouldn't have access to memories:
            
                * "first_token" attends to the latest token that was a first token in some context.
                  Due to causal attention, the first token in a context carries the least meaning.
                  Also, likely for related reasons, inactive attention heads are known to park
                  themselves on the first token. Empirically, this approach seems to work quite
                  well.

                * "all_tokens" attends to all tokens in memory uniformly

        memory_dumper:
            Optional MemoryDumper to persist any added memories.
        """
        self.device = device

        self.training = True

        if memory_dumper_init is None:
            memory_dumper_init = lambda training: None

        self.partition = _MemoryPartition(
            memory_size,
            memory_invalid_query_mode,
            memory_dumper_init(self.training),
        )
        self.inactive_partition = _MemoryPartition(
            memory_size,
            memory_invalid_query_mode,
            memory_dumper_init(not self.training),
        )

    def get_partition(self, training):
        if training != self.training:
            # swap out the memory partitions (training or evaluation)
            self.inactive_partition, self.partition = self.partition, self.inactive_partition

            # move the active partition to the GPU and the inactive one to the CPU
            self.inactive_partition._move_to(torch.device('cpu'))
            self.partition._move_to(self.device)

            # sync the inactive partition (if dumping to file)
            self.inactive_partition._sync()

            self.training = training
            if self.training:
                # Clear the evaluation memory at the end of each evaluation cycle
                self.inactive_partition._clear()

        return self.partition


class _MemoryPartition:
    """
    Partition of key-value memories in a single transformer layer. We expect one partition
    for training and one for evaluation.
    """

    def __init__(self, memory_size, memory_invalid_query_mode, memory_dumper=None):
        self.memory_size = memory_size
        self.memory_invalid_query_mode = memory_invalid_query_mode
        self.memory_dumper = memory_dumper
        self._clear()

    def _move_to(self, device):
        if self.keys is not None:
            self.keys = self.keys.to(device)
            self.values = self.values.to(device)

    def _clear(self):
        self.keys = None
        self.values = None
        self.first_token = None

    def _sync(self):
        if self.memory_dumper is not None:
            self.memory_dumper.sync()

    def add_memories(self, keys, values, eod_markers):
        """
            keys: [sq, b, np, hn]
            values: [sq, b, np, hn]
            eod_markers
        """

        # save the memories to the file, if requested

        if self.memory_dumper is not None:
            self.memory_dumper.dump([
                keys.view(keys.shape[0] * keys.shape[1], keys.shape[2], keys.shape[3]).cpu(),
                values.view(keys.shape[0] * keys.shape[1], keys.shape[2], keys.shape[3]).cpu(),
            ])

        # record the memories

        if self.keys is None:
            self.keys = keys
            self.values = values
            self.valid_from = [0] * len(eod_markers)
            self.first_token = [0] * len(eod_markers)
        else:
            self.keys = torch.cat((self.keys, keys), dim=0)
            self.values = torch.cat((self.values, values), dim=0)

        # invalidate any memories before the newest EOD token

        for i in range(len(eod_markers)):
            # update the "first token"
            self.first_token[i] = self.keys.shape[0] - keys.shape[0]

            # if there are any EOD markers, invalidate the memories up to (but excluding) the last marker
            if eod_markers[i][0] <= eod_markers[i][1]:
                self.valid_from[i] = self.keys.shape[0] - keys.shape[0] + eod_markers[i][1]

        # drop some memories if we already have too much

        if self.keys.shape[0] > self.memory_size:
            # shift the window forward
            removed_count = self.keys.shape[0] - self.memory_size
            self.keys = self.keys[removed_count:]
            self.values = self.values[removed_count:]

            for i in range(len(eod_markers)):
                self.valid_from[i] -= min(self.valid_from[i], removed_count)
                self.first_token[i] -= removed_count

    def get_memories(self, device, is_training, queries, eod_markers):
        # Mask away:
        #    - memorized keys from before EOS
        #    - queries from after EOS

        # memory_mask: [b, head (broadcast), sq, sk]
        memory_mask = torch.full(
            size=(self.keys.shape[1], 1, queries.shape[0], self.keys.shape[0]),
            fill_value=True,
            device=device)

        for batch in range(memory_mask.shape[0]):
            keys_valid_from = self.valid_from[batch]
            queries_valid_to = eod_markers[batch][0]
            memory_mask[batch,:,:queries_valid_to,keys_valid_from:] = False

            if self.memory_invalid_query_mode == "first_token":
                memory_mask[batch,:,queries_valid_to:,self.first_token[batch]] = False
            elif self.memory_invalid_query_mode == "all_tokens":
                memory_mask[batch,:,queries_valid_to:,:] = False
            else:
                raise BaseException("Invalid memory_invalid_query_mode value", self.memory_invalid_query_mode)

        return self.keys, self.values, memory_mask

    def is_empty(self):
        return self.keys is None
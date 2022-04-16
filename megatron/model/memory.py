import torch

class MemoryStore:
    def __init__(self, memory_size, memory_invalid_query_mode, memory_pickler=None):
        self.memory_size = memory_size
        self.memory_invalid_query_mode = memory_invalid_query_mode
        self.memory_pickler = memory_pickler
        self._clear()

    def _move_to(self, device):
        if self.keys is not None:
            self.keys = self.keys.to(device)
            self.values = self.values.to(device)

    def _clear(self):
        self.keys = None
        self.values = None
        self.first_token = None

    def add(self, is_training, keys, values, eod_markers):
        """
            keys: [sq, b, np, hn]
            values: [sq, b, np, hn]
            eod_markers
        """

        # save the memories to the file, if requested

        if self.memory_pickler is not None:
            self.memory_pickler.dump([
                keys.view(keys.shape[0] * keys.shape[1], keys.shape[2], keys.shape[3]),
                values.view(keys.shape[0] * keys.shape[1], keys.shape[2], keys.shape[3]),
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

    def get(self, is_training, query_count, eod_markers):
        # Mask away:
        #    - memorized keys from before EOS
        #    - queries from after EOS

        # memory_mask: [b, 1, sq, sk]
        memory_mask = torch.full(
            size=(self.keys.shape[1], 1, query_count, self.keys.shape[0]),
            fill_value=True,
            device=self.keys.device)

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

class SimpleMemory:
    def __init__(self, device, memory_size, memory_invalid_query_mode, memory_pickler=None):
        self.device = device

        self.training = True

        self.store = MemoryStore(memory_size, memory_invalid_query_mode, memory_pickler)
        self.inactive_store = MemoryStore(memory_size, memory_invalid_query_mode, memory_pickler)

    def get_store(self, training):
        if training != self.training:
            # swap out the memory stores (training or evaluation)
            self.inactive_store, self.store = self.store, self.inactive_store

            # move the active store to the GPU and the inactive one to the CPU
            self.inactive_store._move_to(torch.device('cpu'))
            self.store._move_to(self.device)

            self.training = training
            if self.training:
                # Clear the evaluation memory at the end of each evaluation cycle
                self.inactive_store._clear()

        return self.store

class MemoryPickler:
    def __init__(self, file_name_base, file_bytes_goal, save_file_func=None):
        self.file_name_base = file_name_base
        self.file_bytes_goal = file_bytes_goal
        self.save_file_func = save_file_func

    def dump(self, record):
        # if the current batch is full, close it
        if self.file is not None and self.file.tell() > self.file_bytes_goal:
            self.close()

        # if there is no open batch, create a new one
        if self.file is None:
            self.cur_file_name = "{}.{}".format(self.file_name_base, self.next_file_idx)
            self.file = open(self.cur_file_name, 'wb')
            self.next_file_idx = self.next_file_idx + 1

        # pickle the record into the current batch
        pickle.dump(record, self.file)

    def close(self):
        if self.file != None:
            # close the file
            self.file.close()
            self.file = None

            # compress and upload the file
            if self.save_file_func is not None:
                self.save_file_func(self.cur_file_name)
                if self.cur_file_name and os.path.exists(self.cur_file_name):
                    os.remove(self.cur_file_name)

            # mark the batch as finished
            self.cur_file_name = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

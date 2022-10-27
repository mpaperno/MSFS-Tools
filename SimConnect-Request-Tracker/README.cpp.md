# Summary

 Members                        | Descriptions
--------------------------------|---------------------------------------------
`class `[`SimConnectRequestTracker`](#class_sim_connect_request_tracker) | `SimConnectRequestTracker` provides methods for recording and retrieving data associated with SimConnect function calls.
`struct `[`SimConnectRequestTracker::RequestData`](#struct_sim_connect_request_tracker_1_1_request_data) | SimConnect request (method invocation) tracking record for storing which request caused a simulator error (such as unknown variable/event name, etc).

## class `SimConnectRequestTracker` <a id="class_sim_connect_request_tracker"></a>

`SimConnectRequestTracker` provides methods for recording and retrieving data associated with SimConnect function calls.

When SimConnect sends an exception message (`SIMCONNECT_RECV_ID_EXCEPTION`), it only provides a "send ID" with which to identify what caused the exception in the first place. Since requests are asynchronous, there needs to be some way to record what the original function call was in order to find out what the exception is referring to.

Two primary methods are provided to achieve this goal: [`addRequestRecord()`](#class_sim_connect_request_tracker_1a7dff3cfb516f13bd3c4af75df1386853) and [`getRequestRecord()`](#class_sim_connect_request_tracker_1afc54be1bc74f3736098da3b1b80732d0) which should be fairly self-explanatory. The former is called right after a SimConnect function is invoked and gets the unique "send ID" from SimConnect and saved all data in a cache.<br/>
Use the latter method to find which SimConnect function call caused an exception in the `SIMCONNECT_RECV_ID_EXCEPTION` handler of your message dispatcher. See the respective documentation for further details on each method.

Request data is available as a [`RequestData`](#struct_sim_connect_request_tracker_1_1_request_data) structure, which contains all relevant information about the original function call (method name and arguments list), and also provides convenient output methods like an `ostream <<` operator and a `RequestData::toString()`. Both will show as much data as possible, including the exception name and at which argument the error occurred (the `dwIndex`).

Request data is stored in a "circular buffer" type cache with a configurable maximum number of records stored. After the maximum is reached, records start to be overwritten, starting at the oldest. The amount of memory used for the requests cache can be controlled either in the constructor `maxRecords` argument or using the [`setMaxRecords`()](#class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a) method. This memory is pre-allocated on the stack, and each record takes 440B of stack space. Additional heap (de)allocations will happen at runtime by the `string` and `stringstream` type members of [`RequestData`](#struct_sim_connect_request_tracker_1_1_request_data) as they are created/destroyed dynamically. See docs on [`SimConnectRequestTracker()`](#class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6) c'tor and [`setMaxRecords()`](#class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a) for some more details.

A few convenience methods are also provided for when a request is not tracked (or the record of it wasn't found in cache) or for other logging purposes. A SimConnect exception name can be looked up based on the `dwException` enum value from the exception message struct using the static [`exceptionName()`](#class_sim_connect_request_tracker_1a24d52985d23977ee470d9f190af39828) method.<br/>
A variadic template is also provided for logging any number of argument values to a stream or string, for example to log a returned error right after a SimConnect function call.

All methods in this class are thread-safe if the `SCRT_THREADSAFE` macro == 1, which is the default unless `_LIBCPP_HAS_NO_THREADS` is defined.

<a id="class_sim_connect_request_tracker_1autotoc_md0"></a>

### Examples
ExamplesAssuming that:
```cpp
[SimConnectRequestTracker](#class_sim_connect_request_tracker) g_requestTracker {};
HANDLE hSim;  // handle to an open SimConnect
// some data fields used in the example SimConnect function calls
SIMCONNECT_CLIENT_DATA_DEFINITION_ID cddId;
DWORD szOrType;
float epsilon;
DWORD offset;

// Signature of SimConnect function used in the examples, for reference:
// SimConnect_AddToClientDataDefinition(HANDLE hSimConnect,
//    SIMCONNECT_CLIENT_DATA_DEFINITION_ID DefineID,
//    DWORD dwOffset,
//    DWORD dwSizeOrType,
//    float fEpsilon = 0,
//    DWORD DatumID = SIMCONNECT_UNUSED
// )
```

Basic usage:
```cpp
// Make a SimConnect function call somewhere in your code and save the request record.
HRESULT hr = SimConnect_AddToClientDataDefinition(hSim, cddId, offset, szOrType, epsilon);
if FAILED(hr)
  std::cerr << "SimConnect_AddToClientDataDefinition("  << cddId << ',' << szOrType << ',' << offset << ',' << epsilon << ") failed with " << hr << std::endl;
else
  g_requestTracker.addRequestRecord(hSim, "SimConnect_AddToClientDataDefinition", cddId, szOrType, offset, epsilon);

// ...
// In your SimConnect message dispatch handler you can then retrieve the saved function call if a `SIMCONNECT_RECV_ID_EXCEPTION` type message is received.
void simConnectMessageDispatch(SIMCONNECT_RECV *pData, DWORD cbData) {
  switch (pData->dwID) {
    // ...  other handlers
    case SIMCONNECT_RECV_ID_EXCEPTION:
      std::cerr << "SimConnect exception: " << g_requestTracker->getRequestRecord(pData->dwSendID, pData->dwException, pData->dwIndex);
      break;
  }
}
```

This next example shows how to set up a "proxy" template which will call any SimConnect function passed to it, using any number of arguments, log any immediate error or add a tracking record, and return the `HRESULT`.

```cpp
// Main SimConnect function invoker template which does the actual call, logs any error or creates a request record, and returns the HRESULT from SimConnect.
// The first argument, `fname`, is the function name that is being called, as a string, for logging purposes. It can be any string actually, perhaps a full function signature.
// The other arguments are a pointer to the function, a handle to SimConnect, and any further arguments passed along to SimConnect in the function call.
template<typename... Args>
static HRESULT simConnectProxy(const char *fname, std::function<HRESULT(HANDLE, Args...)> f, HANDLE hSim, Args... args) {
  const HRESULT hr = std::bind(f, std::forward<HANDLE>(hSim), std::forward<Args>(args)...)();
  if FAILED(hr)
    std::cerr << "Error: " << fname << '(' << SimConnectRequestTracker::printArgs(args...) << ") failed with " << hr << std::endl;
  else
    simRequestTracker().addRequestRecord(hSim, fname, args...);
  return hr;
}

// Because we really want type deduction, we can invoke simConnectProxy() via this template w/out specifying each argument type for the `simConnectProxy<>()` call.
template<typename... Args>
static HRESULT invokeSimConnect(const char *fname, HRESULT(*f)(HANDLE, Args...), HANDLE hSim, Args... args) {
  return simConnectProxy(fname, std::function<HRESULT(HANDLE, Args...)>(f), hSim, args...);
}

// The macro allows us to only pass the function name once to get both the name string and the actual callable. Optional.
#define INVOKE_SIMCONNECT(F, ...)  invokeSimConnect(#F, &F, __VA_ARGS__)

// ... then use the macro to make the call, or if you don't like macros, or want to use a specific function name (perhaps with signature), specify the name of the function yourself.
// **Note** that unless you're using c++20 (or higher), for the template function type deduction to work, the arguments list and types need to match the SimConnect function signature _exactly_.
// Including any optional arguments (the last 2 in this example).  C++20 apparently improves the deduction rules but I haven't personally tested it.
INVOKE_SIMCONNECT(SimConnect_AddToClientDataDefinition, hSim, cddId, offset, szOrType, epsilon, SIMCONNECT_UNUSED);
// invokeSimConnect("AddToClientDataDefinition(DefineID, dwOffset, dwSizeOrType, fEpsilon, DatumID)", &SimConnect_AddToClientDataDefinition, hSim, cddId, offset, szOrType, epsilon, SIMCONNECT_UNUSED);
```

### Summary

 Members                        | Descriptions
--------------------------------|---------------------------------------------
`public inline  explicit `[`SimConnectRequestTracker`](#class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6)`(uint32_t maxRecords)` | Construct an instance of the tracker. Typically only one global/static instance should track all requests, but this is not required (each tracker instance keeps its own log of requests, they are not shared between instances).
`public inline void `[`setMaxRecords`](#class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a)`(uint32_t maxRecords)` | Sets the maximum number of request records stored in the cache. See description of the `maxRecords` argument in [`SimConnectRequestTracker()`](#class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6) constructor for details. If this value is reduced from the original (starting) value, all records stored at indexes past the new maximum will be deleted, which may include the most recent records (they are stored in a round-robin fashion so the current "write slot" may by anywhere in the cache at any given moment).
`public template<>`  <br/>`inline void `[`addRequestRecord`](#class_sim_connect_request_tracker_1a7dff3cfb516f13bd3c4af75df1386853)`(HANDLE hSim, std::string && methodInfo, Args... args)` | Makes a record of a SimConnect request. Needs a handle to SimConnect to get the last sent ID, which it saves along with the passed SimConnect function name and any number of arguments which were originally passed to whatever SimConnect function was called. If needed, the record can later be checked using the `dwSendId` from SimConnect's exception message and the original call which caused the exception can be logged.
`public inline `[`RequestData`](#struct_sim_connect_request_tracker_1_1_request_data)` const & `[`getRequestRecord`](#class_sim_connect_request_tracker_1afc54be1bc74f3736098da3b1b80732d0)`(uint32_t dwSendId, uint32_t ex, uint32_t idx)` | Try to find and return a request record for the given dwSendId. If no record is found, returns a reference to a static instance which is empty (no method or argument details) except for the dwSendID and exception/index (if passed in to this method).
`public template<>`  <br/>`inline static void `[`streamArgs`](#class_sim_connect_request_tracker_1a07d97f8294bdac74bcf1ccf0ff968ad3)`(std::ostream & os, T var1, Args... var2)` | Recursively output all arguments to a stream, with comma separator between each (no spaces). Args types must have stream operators, obviously.
`public template<>`  <br/>`inline static std::string `[`printArgs`](#class_sim_connect_request_tracker_1adb20aaacfee24e6118e7d60d4ffe898c)`(Args... args)` | Outputs all arguments to a string with comma separators. Args types must have stream operators (uses [`streamArgs()`](#class_sim_connect_request_tracker_1a07d97f8294bdac74bcf1ccf0ff968ad3) to create a string).
`public inline static const char *const `[`exceptionName`](#class_sim_connect_request_tracker_1a24d52985d23977ee470d9f190af39828)`(uint32_t id)` | Get SimConnect exception name (enum as string) from ID enum. Omits the "SIMCONNECT_EXCEPTION" part.

### Members

#### `public inline  explicit `[`SimConnectRequestTracker`](#class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6)`(uint32_t maxRecords)` <a id="class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6"></a>

Construct an instance of the tracker. Typically only one global/static instance should track all requests, but this is not required (each tracker instance keeps its own log of requests, they are not shared between instances).

#### Parameters
* `maxRecords` The maximum number of request records to store in the cache. If many requests are made in fast succession (like at the startup of a SimConnect client requesting a lot of data value subscriptions), some records may get lost (overwritten) by the time SimConnect manages to send an exception message. On the other hand for low volume usage, memory can be saved by reducing the number of stored records. This property can also be changed during runtime using [`setMaxRecords()`](#class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a) method.

#### `public inline void `[`setMaxRecords`](#class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a)`(uint32_t maxRecords)` <a id="class_sim_connect_request_tracker_1af4249e85a58d467103f63b4b1271f94a"></a>

Sets the maximum number of request records stored in the cache. See description of the `maxRecords` argument in [`SimConnectRequestTracker()`](#class_sim_connect_request_tracker_1afbc5febed03520a73d356d348523cfa6) constructor for details. If this value is reduced from the original (starting) value, all records stored at indexes past the new maximum will be deleted, which may include the most recent records (they are stored in a round-robin fashion so the current "write slot" may by anywhere in the cache at any given moment).

#### `public template<>`  <br/>`inline void `[`addRequestRecord`](#class_sim_connect_request_tracker_1a7dff3cfb516f13bd3c4af75df1386853)`(HANDLE hSim, std::string && methodInfo, Args... args)` <a id="class_sim_connect_request_tracker_1a7dff3cfb516f13bd3c4af75df1386853"></a>

Makes a record of a SimConnect request. Needs a handle to SimConnect to get the last sent ID, which it saves along with the passed SimConnect function name and any number of arguments which were originally passed to whatever SimConnect function was called. If needed, the record can later be checked using the `dwSendId` from SimConnect's exception message and the original call which caused the exception can be logged.

#### `public inline `[`RequestData`](#struct_sim_connect_request_tracker_1_1_request_data)` const & `[`getRequestRecord`](#class_sim_connect_request_tracker_1afc54be1bc74f3736098da3b1b80732d0)`(uint32_t dwSendId, uint32_t ex, uint32_t idx)` <a id="class_sim_connect_request_tracker_1afc54be1bc74f3736098da3b1b80732d0"></a>

Try to find and return a request record for the given dwSendId. If no record is found or the cache is disabled entirely, then it returns a reference to a static instance (which has no method or argument details) populated with the given `dwSendID`, `ex`, and `idx` parameters.

#### Parameters
* `dwSendId` The `dwSendId` to look up, typically from the `SIMCONNECT_RECV_EXCEPTION.dwSendId` struct member.

* `ex` SimeConnect exception ID, typically from the `SIMCONNECT_RECV_EXCEPTION.dwException` member. This is stored in the returned RequestRecord, and is resolved to a string name (with [`exceptionName()`](#class_sim_connect_request_tracker_1a24d52985d23977ee470d9f190af39828)) for display with the `RequestData::toString()` or stream operator methods.

* `idx` SimeConnect exception parameter index, typically from the `SIMCONNECT_RECV_EXCEPTION.dwIndex` member. This is stored in the returned RequestRecord and is displayed in the `RequestData::toString()` or stream operator method outputs.

**NOTE:** The returned reference should stay in scope unless the cache is shrunk (and that index gets deleted). However the data could change at any point if the cache storage slot is reused for a new request. Or, in the cases where a reference to a static instance is returned, the next `getRequestRecord()` call will overwrite the static data from the previous call. All this to say: **do not store the reference.**

#### `public template<>`  <br/>`inline static void `[`streamArgs`](#class_sim_connect_request_tracker_1a07d97f8294bdac74bcf1ccf0ff968ad3)`(std::ostream & os, T var1, Args... var2)` <a id="class_sim_connect_request_tracker_1a07d97f8294bdac74bcf1ccf0ff968ad3"></a>

Recursively output all arguments to a stream, with comma separator between each (no spaces). Args types must have stream operators, obviously.

#### `public template<>`  <br/>`inline static std::string `[`printArgs`](#class_sim_connect_request_tracker_1adb20aaacfee24e6118e7d60d4ffe898c)`(Args... args)` <a id="class_sim_connect_request_tracker_1adb20aaacfee24e6118e7d60d4ffe898c"></a>

Outputs all arguments to a string with comma separators. Args types must have stream operators (uses [`streamArgs()`](#class_sim_connect_request_tracker_1a07d97f8294bdac74bcf1ccf0ff968ad3)`to create a string).

#### `public inline static const char *const `[`exceptionName`](#class_sim_connect_request_tracker_1a24d52985d23977ee470d9f190af39828)`(uint32_t id)` <a id="class_sim_connect_request_tracker_1a24d52985d23977ee470d9f190af39828"></a>

Get SimConnect exception name (enum as string) from ID enum. Omits the "SIMCONNECT_EXCEPTION" part.

## struct `SimConnectRequestTracker::RequestData` <a id="struct_sim_connect_request_tracker_1_1_request_data"></a>

SimConnect request (method invocation) tracking record for storing which request caused a simulator error (such as unknown variable/event name, etc).

### Summary

 Members                        | Descriptions
--------------------------------|---------------------------------------------
`public std::string `[`sMethod`](#struct_sim_connect_request_tracker_1_1_request_data_1a47e437b61c9187f3f9be7091067af218) | Name of the function/method which was invoked.
`public std::stringstream `[`ssArguments`](#struct_sim_connect_request_tracker_1_1_request_data_1ab640bbcc33d0e7f9e7c2e1718a04644e) | Parameter argument values passed in the invoker method. Stored in an I/O stream for potential retrieval as individual values.
`public uint32_t `[`dwSendId`](#struct_sim_connect_request_tracker_1_1_request_data_1a2502dde53d131849f65f3cea301eb1dc) | The "dwSendId" from SimConnect_GetLastSentPacketID() and referenced in the `SIMCONNECT_RECV_EXCEPTION.dwSendId` struct member.
`public SIMCONNECT_EXCEPTION `[`eException`](#struct_sim_connect_request_tracker_1_1_request_data_1a064732f5636cda8a7b5e327582a254ba) | Associated exception, if any, from `SIMCONNECT_RECV_EXCEPTION.dwException` member.
`public uint32_t `[`dwExceptionIndex`](#struct_sim_connect_request_tracker_1_1_request_data_1a23fb773f36cd6ea363ed4c01c48d0e48) | The index number of the first parameter that caused an error, if any, from `SIMCONNECT_RECV_EXCEPTION.dwIndex`. 0 if unknown and index starts at 1, which is the first argument after the HANDLE pointer. Note that `SIMCONNECT_RECV_EXCEPTION.dwIndex` may sometimes be -1 which means none of the arguments specifically caused the error (usually due to a previous error).
`public uint8_t `[`argsCount`](#struct_sim_connect_request_tracker_1_1_request_data_1aacea75db8f78c115eda2a82ffe786a93) | Number of arguments in arguments stream.
`public inline std::string `[`ToString`](#struct_sim_connect_request_tracker_1_1_request_data_1a78b6f0b3bee63b18ad8d3529279aeea6)`()` | Returns formatted information about the method invocation which triggered the request, and the SimConnect error, if any. Uses the `ostream <<` operator to generate the string.

### Members

#### `public std::string `[`sMethod`](#struct_sim_connect_request_tracker_1_1_request_data_1a47e437b61c9187f3f9be7091067af218) <a id="struct_sim_connect_request_tracker_1_1_request_data_1a47e437b61c9187f3f9be7091067af218"></a>

Name of the function/method which was invoked.

#### `public std::stringstream `[`ssArguments`](#struct_sim_connect_request_tracker_1_1_request_data_1ab640bbcc33d0e7f9e7c2e1718a04644e) <a id="struct_sim_connect_request_tracker_1_1_request_data_1ab640bbcc33d0e7f9e7c2e1718a04644e"></a>

Parameter argument values passed in the invoker method. Stored in an I/O stream for potential retrieval as individual values.

#### `public uint32_t `[`dwSendId`](#struct_sim_connect_request_tracker_1_1_request_data_1a2502dde53d131849f65f3cea301eb1dc) <a id="struct_sim_connect_request_tracker_1_1_request_data_1a2502dde53d131849f65f3cea301eb1dc"></a>

The "dwSendId" from SimConnect_GetLastSentPacketID() and referenced in the `SIMCONNECT_RECV_EXCEPTION.dwSendId` struct member.

#### `public SIMCONNECT_EXCEPTION `[`eException`](#struct_sim_connect_request_tracker_1_1_request_data_1a064732f5636cda8a7b5e327582a254ba) <a id="struct_sim_connect_request_tracker_1_1_request_data_1a064732f5636cda8a7b5e327582a254ba"></a>

Associated exception, if any, from `SIMCONNECT_RECV_EXCEPTION.dwException` member.

#### `public uint32_t `[`dwExceptionIndex`](#struct_sim_connect_request_tracker_1_1_request_data_1a23fb773f36cd6ea363ed4c01c48d0e48) <a id="struct_sim_connect_request_tracker_1_1_request_data_1a23fb773f36cd6ea363ed4c01c48d0e48"></a>

The index number of the first parameter that caused an error, if any, from `SIMCONNECT_RECV_EXCEPTION.dwIndex`. 0 if unknown and index starts at 1, which is the first argument after the HANDLE pointer. Note that `SIMCONNECT_RECV_EXCEPTION.dwIndex` may sometimes be -1 which means none of the arguments specifically caused the error (usually due to a previous error).

#### `public uint8_t `[`argsCount`](#struct_sim_connect_request_tracker_1_1_request_data_1aacea75db8f78c115eda2a82ffe786a93) <a id="struct_sim_connect_request_tracker_1_1_request_data_1aacea75db8f78c115eda2a82ffe786a93"></a>

Number of arguments in arguments stream.

#### `public inline std::string `[`ToString`](#struct_sim_connect_request_tracker_1_1_request_data_1a78b6f0b3bee63b18ad8d3529279aeea6)`()` <a id="struct_sim_connect_request_tracker_1_1_request_data_1a78b6f0b3bee63b18ad8d3529279aeea6"></a>

Returns formatted information about the method invocation which triggered the request, and the SimConnect error, if any. Uses the `ostream <<` operator to generate the string.

### Related Non-Members

#### `friend inline `[`std::ostream& operator<<`]()`(std::ostream&, const RequestData &)` <a id="struct_sim_connect_request_tracker_1_1_request_data_streamop"></a>

Streams formatted information about the method invocation which triggered the request, if any is found, and the SimConnect error, if any.

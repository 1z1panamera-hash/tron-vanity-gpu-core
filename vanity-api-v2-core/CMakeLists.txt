cmake_minimum_required(VERSION 3.16)
project(vanity_api_v2_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(tron_pattern STATIC src/tron_pattern.cpp)
target_include_directories(tron_pattern PUBLIC include)
target_compile_options(tron_pattern PRIVATE -Wall -Wextra -Werror)

add_library(worker_protocol STATIC src/worker_protocol.cpp)
target_include_directories(worker_protocol PUBLIC include)
target_compile_options(worker_protocol PRIVATE -Wall -Wextra -Werror)

add_library(core_security STATIC src/core_security.cpp)
target_include_directories(core_security PUBLIC include)
target_compile_options(core_security PRIVATE -Wall -Wextra -Werror)

find_package(SQLite3 REQUIRED)
add_library(worker_outbox STATIC src/worker_outbox.cpp)
target_include_directories(worker_outbox PUBLIC include)
target_link_libraries(worker_outbox PUBLIC SQLite::SQLite3)
target_compile_options(worker_outbox PRIVATE -Wall -Wextra -Werror)

add_executable(test_tron_pattern tests/test_tron_pattern.cpp)
target_link_libraries(test_tron_pattern PRIVATE tron_pattern)
target_compile_options(test_tron_pattern PRIVATE -Wall -Wextra -Werror)

add_executable(test_worker_protocol tests/test_worker_protocol.cpp)
target_link_libraries(test_worker_protocol PRIVATE worker_protocol)
target_compile_options(test_worker_protocol PRIVATE -Wall -Wextra -Werror)

add_executable(test_core_security tests/test_core_security.cpp)
target_link_libraries(test_core_security PRIVATE core_security)
target_compile_options(test_core_security PRIVATE -Wall -Wextra -Werror)

add_executable(test_worker_outbox tests/test_worker_outbox.cpp)
target_link_libraries(test_worker_outbox PRIVATE worker_outbox)
target_compile_options(test_worker_outbox PRIVATE -Wall -Wextra -Werror)

enable_testing()
add_test(NAME tron_pattern COMMAND test_tron_pattern)
add_test(NAME worker_protocol COMMAND test_worker_protocol)
add_test(NAME core_security COMMAND test_core_security)
add_test(NAME worker_outbox COMMAND test_worker_outbox)

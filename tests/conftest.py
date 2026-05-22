# tests/conftest.py
"""
pytest fixtures for navisv tests
"""

import pytest
import os


@pytest.fixture(scope='session')
def test_signal_attrs_content():
    """Test signal attributes SV content"""
    return '''// Test case: signal_attributes verification
// Includes: register outputs, combinational, clock domains, reset conditions
module test_signal_attributes (
    input wire clk,
    input wire clk2,
    input wire rst_n,
    input wire [7:0] a,
    input wire [7:0] b,
    input wire [2:0] sel,
    input wire enable,
    input wire load,
    input wire [7:0] data_in,
    output reg [7:0] result
);

    // 1. Register with async reset + if-else
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            result <= 8'h00;
        else if (enable)
            result <= a + b;
        else if (load)
            result <= data_in;
        else
            result <= 8'h00;
    end

    // 2. Register with sync reset
    reg [7:0] case_out;
    always @(posedge clk) begin
        if (!rst_n)
            case_out <= 8'h00;
        else case (sel)
            3'b000: case_out <= a;
            3'b001: case_out <= b;
            3'b010: case_out <= data_in;
            default: case_out <= 8'h00;
        endcase
    end

    // 3. Register with async reset, no else
    reg [7:0] complex_reg;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            complex_reg <= 8'h00;
        else if (enable)
            complex_reg <= a + b;
    end

    // 4. Register without reset
    reg [7:0] no_reset_reg;
    always @(posedge clk2)
        no_reset_reg <= data_in;

    // 5. Ternary operator wire
    wire [7:0] complex_result = enable ? a + b : 8'h00;

endmodule
'''


@pytest.fixture(scope='session')
def test_signal_attrs_file(tmp_path_factory, test_signal_attrs_content):
    """Create a temporary test_signal_attrs.sv file"""
    test_dir = tmp_path_factory.mktemp("test_sv")
    file_path = test_dir / "test_signal_attrs.sv"
    file_path.write_text(test_signal_attrs_content)
    return str(file_path)


@pytest.fixture(scope='session')
def test_apb_uart_content():
    """Test APB UART with errors"""
    return '''// Test APB UART with intentional errors
module apb_uart (
    input wire pclk,
    input wire presetn,
    input wire [31:0] paddr,
    input wire pwrite,
    input wire [31:0] pwdata,
    input wire [31:0] prdata,
    input wire psel,
    input wire penable,
    output reg [7:0] tx_data
);

    typedef enum logic [2:0] {
        RX_DATA    = 3'b106,  // ERROR: binary digit out of range
        RX_STOP    = 3'b107,  // ERROR
        RX_STOP    = 3'b108,  // ERROR: redefined
        IDLE       = 3'b000
    } rx_state_t;

    always @(posedge pclk or negedge presetn) begin
        if (!presetn)
            tx_data <= 8'h00;
        else
            tx_data <= pwdata[7:0];
    end

endmodule
'''


@pytest.fixture(scope='session')
def test_apb_uart_file(tmp_path_factory, test_apb_uart_content):
    """Create a temporary test_apb_uart.sv file with errors"""
    test_dir = tmp_path_factory.mktemp("test_sv")
    file_path = test_dir / "test_apb_uart.sv"
    file_path.write_text(test_apb_uart_content)
    return str(file_path)


@pytest.fixture(scope='session')
def test_filelist_content():
    """Test filelist content"""
    return '''/tmp/test_signal_attrs.sv
/tmp/test_signal_attrs.sv
'''


@pytest.fixture(scope='session')
def test_filelist_file(tmp_path_factory, test_filelist_content):
    """Create a temporary filelist"""
    test_dir = tmp_path_factory.mktemp("test_filelist")
    file_path = test_dir / "test_filelist.f"
    file_path.write_text(test_filelist_content)
    return str(file_path)


# 提供旧路径作为后备（用于向后兼容某些测试）
@pytest.fixture(scope='session')
def legacy_test_signal_attrs():
    """Legacy path for test_signal_attrs.sv"""
    return '/tmp/test_signal_attrs.sv'


@pytest.fixture(scope='session')
def legacy_test_apb_uart():
    """Legacy path for test_apb_uart.sv"""
    return '/tmp/test_apb_uart.sv'


@pytest.fixture(scope='session')
def legacy_test_filelist():
    """Legacy path for filelist"""
    return '/tmp/test_filelist.f'